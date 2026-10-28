"""ROX-Chat unified architecture (500M/1B track).

Fuses the llm_500m data factory with ROX-N surprise-gated mechanisms.
Deliberately carries over ONLY what was validated; the rox_m emotion
mechanisms were never trained (per audit) and stay out.

Per-layer FFN is EME-routed MoE on moe_every-th layers, dense SwiGLU
elsewhere. Two execution modes because training is parallel while
inference streams (the hidden crux of gated architectures):

  TRAIN (parallel, teacher-forced):
    FOU  = dense FFN + sparsity aux loss on per-token importance
           (learns WHICH tokens matter; hard caches can't exist
           without sequential positions — specified approximation,
           validated by the Stage-0 infer/train parity gate).
    EME  = standard top-2 gating + load-balance aux loss.
  INFER (streaming, KV-style caches):
    FOU  = hard top-k surprise caches (rox_n proven logic).
    EME  = hysteresis: incumbent bonus + surprise-forced re-eval.

Position: RoPE default. PLHE available via position='plhe' (phase-
integrated helix over token-embedding novelty); Stage-0 decides whether
it survives — fallback is RoPE with FOU/EME intact, per training plan.
"""
import math
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass(frozen=True)
class Cfg:
    layers: int = 20
    d: int = 1024
    heads: int = 8
    ffn_mult: float = 2.75       # SwiGLU hidden = mult*d (params ~3*d*h)
    experts: int = 8
    topk: int = 2
    moe_every: int = 4           # every Nth layer is MoE, rest dense
    vocab: int = 32000
    ctx: int = 2048
    position: str = "rope"       # rope | plhe
    fou_topk_frac: float = 0.25  # inference firing budget (Stage-0 tuned)
    eme_lambda: float = 2.0      # inference hysteresis bonus


CFG_500M = Cfg(layers=18, d=960, heads=8, experts=8, moe_every=4)
CFG_1B = Cfg(layers=24, d=1216, heads=8, experts=8, moe_every=4)
CFG_TINY = Cfg(layers=4, d=128, heads=4, experts=4, moe_every=2,
               vocab=256, ctx=128)  # CPU Stage-0, byte-level
# 500M byte-level from scratch (no tokenizer needed)
CFG_500M_BYTE = Cfg(layers=18, d=960, heads=8, experts=8, moe_every=4,
                    vocab=256, ctx=512)


class SwiGLU(nn.Module):
    def __init__(self, d, h):
        super().__init__()
        self.w1 = nn.Linear(d, h, bias=False)
        self.w2 = nn.Linear(h, d, bias=False)
        self.w3 = nn.Linear(d, h, bias=False)
        self.d, self.h = d, h

    def forward(self, x):
        return self.w2(F.silu(self.w1(x)) * self.w3(x))

    def unit_forward(self, x, idx):
        """Recompute a subset of intermediate units (FOU firing)."""
        a = F.silu(F.linear(x, self.w1.weight[idx])) \
            * F.linear(x, self.w3.weight[idx])
        return F.linear(a, self.w2.weight[:, idx])


class FOUFFN(nn.Module):
    """SwiGLU wrapped in hard top-k surprise caches (inference path).

    Per intermediate unit: s_i = ||x - x_cache_i||_2. Fire top-k units
    over threshold; the rest return cached contributions. train() uses
    the dense forward (see Block); reset_cache() before each sequence.
    Reports min-unit surprise upward for the shared S_t.
    """

    def __init__(self, d, h, topk_frac=0.25, thr=0.5):
        super().__init__()
        self.core = SwiGLU(d, h)
        self.topk_frac = topk_frac
        self.thr = thr
        self.register_buffer("x_cache", torch.zeros(h, d))
        self.register_buffer("y_cache", torch.zeros(h, d))
        self.register_buffer("init", torch.zeros(h, dtype=torch.bool))
        self.fired_steps = 0
        self.total_steps = 0

    def reset_cache(self):
        self.x_cache.zero_()
        self.y_cache.zero_()
        self.init.zero_()
        self.fired_steps = 0
        self.total_steps = 0

    def forward(self, x):
        return self.core(x)  # train path: dense

    @torch.no_grad()
    def step(self, x):
        """x: [d] single token hidden. Returns (out [d], min_surprise)."""
        assert x.dim() == 1
        if not bool(self.init.any()):
            self.x_cache[:] = x
            self.init.fill_(True)
        s = (self.x_cache - x).norm(dim=1)
        k = max(1, int(self.topk_frac * s.shape[0]))
        elig = torch.nonzero(s > self.thr, as_tuple=False).flatten()
        out = self.y_cache.clone()
        if elig.numel():
            order = torch.argsort(s[elig], descending=True)[:k]
            fired = elig[order]
            new = self.core.unit_forward(x, fired)
            out[fired] = new
            self.x_cache[fired] = x
            self.y_cache[fired] = new
            self.init[fired] = True
            self.fired_steps += len(fired)
        self.total_steps += s.shape[0]
        return out.sum(0), float(s.min())

    def active_frac(self):
        return self.fired_steps / max(1, self.total_steps)


class EME(nn.Module):
    """MoE with mode-dependent routing. Experts are FOU-wrapped SwiGLU."""

    def __init__(self, cfg: Cfg, governor=None, layer_id=0):
        super().__init__()
        h = int(cfg.d * cfg.ffn_mult)
        self.experts = nn.ModuleList(FOUFFN(cfg.d, h)
                                     for _ in range(cfg.experts))
        self.gate = nn.Linear(cfg.d, cfg.experts, bias=False)
        self.cfg = cfg
        self.prev = None  # inference incumbent
        self.governor = governor
        self.layer_id = layer_id

    def reset_infer(self):
        for e in self.experts:
            e.reset_cache()
        self.prev = None

    def forward(self, x, surprise=None, infer=False):
        if infer:
            return self._infer(x, surprise)
        # TRAIN: standard top-k + balance aux loss (differentiable).
        # FOUFFN.forward is the dense core, so experts train dense.
        logits = self.gate(x)
        w = torch.softmax(logits, dim=-1)
        topw, topi = torch.topk(w, self.cfg.topk, dim=-1)
        topw = topw / topw.sum(-1, keepdim=True)
        outs = torch.stack([e(x) for e in self.experts], dim=-2)
        w2 = torch.zeros_like(w).scatter_(-1, topi, topw)
        out = (w2.unsqueeze(-1) * outs).sum(-2)
        # balance aux: mean gate mass should be uniform
        balance = (w.mean(dim=tuple(range(w.dim() - 1)))
                   .pow(2).mean() * self.cfg.experts)
        hard = topi[..., 0]
        util = [(hard == i).float().mean().item()
                for i in range(self.cfg.experts)]
        return out, balance, util

    @torch.no_grad()
    def _infer(self, x, surprise):
        # x: [d] single streaming token. Surprise-gated hysteresis.
        # surprise = (global S_prev - thr); <= 0 means calm -> echo.
        # Governor override: None forces re-eval (collapse escape).
        lam = self.cfg.eme_lambda
        if self.governor is not None:
            lam = self.governor.query(self.layer_id)
        logits = self.gate(x)
        if lam is not None and self.prev is not None \
                and surprise is not None and surprise <= 0:
            e = self.prev
            out, _ = self.experts[e].step(x)
            return out, e, False, 0.0
        if lam is not None and self.prev is not None:
            logits[self.prev] += lam
        w = torch.softmax(logits, dim=-1)
        topw, topi = torch.topk(w, self.cfg.topk)
        topw = topw / topw.sum()
        out = torch.zeros_like(x)
        smin = 1e9
        for k in range(self.cfg.topk):
            o, s = self.experts[int(topi[k])].step(x)
            out = out + float(topw[k]) * o
            smin = min(smin, s)
        self.prev = int(topi[0])
        return out, self.prev, True, smin

    def forward_last(self, f, s_minus_thr):
        """Streaming step: only the last row is real; rest are zeros.
        Returns (out [T,d] with real last row, expert, reeval, layer_S)."""
        out = torch.zeros_like(f)
        o, e, r, s = self._infer(f[-1], s_minus_thr)
        out[-1] = o
        return out, e, r, s


class Block(nn.Module):
    def __init__(self, cfg: Cfg, moe: bool, governor=None, layer_id=0):
        super().__init__()
        self.ln1 = nn.LayerNorm(cfg.d)
        self.ln2 = nn.LayerNorm(cfg.d)
        self.attn = nn.MultiheadAttention(cfg.d, cfg.heads,
                                          batch_first=True)
        self.moe = moe
        h = int(cfg.d * cfg.ffn_mult)
        self.ffn = EME(cfg, governor, layer_id) if moe else FOUFFN(cfg.d, h)
        self.cfg = cfg
        # Cast to bf16 after init (LayerNorm stays fp32 for CPU compat)
        self._cast = True

    def reset_infer(self):
        if self.moe:
            self.ffn.reset_infer()
        else:
            self.ffn.reset_cache()

    def forward(self, x, mask, sink=None):
        B, T, _ = x.shape
        # LayerNorm must be fp32 on CPU; cast before, cast back after.
        h1 = self.ln1(x.float()).to(x.dtype)
        a, _ = self.attn(h1, h1, h1, attn_mask=mask)
        x = x + a
        h = self.ln2(x.float()).to(x.dtype)
        if self.moe:
            out, balance, util = self.ffn(h)
            if sink is not None:
                sink["balance"] = sink.get("balance", 0.0) + balance
            return x + out, balance, util
        # FOU training approximation: dense + importance aux loss.
        imp = torch.sigmoid(h.mean(-1))  # [B, T] which tokens matter
        out = self.ffn(h)
        sparse_aux = imp.mean()  # pushed down; coverage loss does the rest
        if sink is not None:
            sink["sparse"] = sink.get("sparse", 0.0) + sparse_aux
        return x + out * imp.unsqueeze(-1), sparse_aux, None

    @torch.no_grad()
    def forward_last(self, x, mask, s_minus_thr):
        """Streaming step over prefix x [1,T,d]: dense attention, hard
        FOU/EME only on the last row. Returns (x_full, layer_S)."""
        h1 = self.ln1(x.float()).to(x.dtype)
        a, _ = self.attn(h1, h1, h1, attn_mask=mask)
        x = x + a
        h = self.ln2(x.float()).to(x.dtype)
        if self.moe:
            out, e, r, s = self.ffn.forward_last(h[0], s_minus_thr)
            return x + out.unsqueeze(0), s, int(r)
        out = torch.zeros_like(h)
        o, s = self.ffn.step(h[0, -1])
        out[0, -1] = o
        return x + out, s, 0


class RoxChat(nn.Module):
    def __init__(self, cfg: Cfg, governor=None):
        super().__init__()
        self.cfg = cfg
        self.tok = nn.Embedding(cfg.vocab, cfg.d)
        self.blocks = nn.ModuleList(
            Block(cfg, moe=(i % cfg.moe_every == cfg.moe_every - 1),
                  governor=governor, layer_id=i)
            for i in range(cfg.layers))
        self.governor = governor
        self.ln = nn.LayerNorm(cfg.d)
        self.head = nn.Linear(cfg.d, cfg.vocab, bias=False)
        self.apply(self._init)

    @staticmethod
    def _init(m):
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, std=0.02)

    def forward(self, idx):
        B, T = idx.shape
        x = self.tok(idx)
        if self.cfg.position == "rope":
            x = apply_rope(x)
        else:
            x = apply_plhe(x)
        mask = torch.triu(torch.ones(T, T, dtype=torch.bool,
                                     device=idx.device), diagonal=1)
        aux, utils = 0.0, []
        for b in self.blocks:
            x, a, u = b(x, mask)
            aux = aux + a
            if u is not None:
                utils.append(u)
        return self.head(self.ln(x.float()).to(x.dtype)), aux, utils

    def forward_parts(self, idx):
        """Same math as forward, but aux split by mechanism family.
        Returns (logits, {'balance': t, 'sparse': t}, utils). Existing
        callers untouched; FIM uses this for per-mechanism gradients."""
        B, T = idx.shape
        x = self.tok(idx)
        if self.cfg.position == "rope":
            x = apply_rope(x)
        else:
            x = apply_plhe(x)
        mask = torch.triu(torch.ones(T, T, dtype=torch.bool,
                                     device=idx.device), diagonal=1)
        sink, utils = {}, []
        for b in self.blocks:
            x, _, u = b(x, mask, sink=sink)
            if u is not None:
                utils.append(u)
        parts = {"balance": sink.get("balance", torch.tensor(0.0)),
                 "sparse": sink.get("sparse", torch.tensor(0.0))}
        return self.head(self.ln(x.float()).to(x.dtype)), parts, utils

    def n_params(self):
        return sum(p.numel() for p in self.parameters())

    def reset_infer(self):
        for b in self.blocks:
            b.reset_infer()

    @torch.no_grad()
    def forward_infer(self, idx, s_minus_thr=0.0):
        """One streaming step over prefix idx [1,T]. Returns
        (logits_last [V], S_global, n_reeval). No KV cache (recompute;
        production needs the KV rewrite — documented, not hidden)."""
        T = idx.shape[1]
        x = self.tok(idx)
        x = apply_rope(x) if self.cfg.position == "rope" \
            else apply_plhe(x)
        mask = torch.triu(torch.ones(T, T, dtype=torch.bool,
                                     device=idx.device), diagonal=1)
        S, reeval = [], 0
        for b in self.blocks:
            x, s, r = b.forward_last(x, mask, s_minus_thr)
            S.append(s)
            reeval += r
        Sg = sum(S) / max(1, len(S))
        return self.head(self.ln(x.float()).to(x.dtype))[0, -1], Sg, reeval

    def active_per_token(self):
        """Analytic active params/token at inference (topk experts only)."""
        c = self.cfg
        h = int(c.d * c.ffn_mult)
        per_expert = 3 * c.d * h
        attn = 4 * c.d * c.d
        dense_ffn = 3 * c.d * h
        n_moe = sum(1 for i in range(c.layers)
                    if i % c.moe_every == c.moe_every - 1)
        n_dense = c.layers - n_moe
        per_tok = c.layers * attn + n_dense * dense_ffn \
            + n_moe * c.topk * per_expert
        return per_tok


def apply_rope(x):
    # Rotary position embedding (standard, Su et al. 2021).
    B, T, d = x.shape
    inv = 1.0 / (10000 ** (torch.arange(0, d, 2, device=x.device)
                           .float() / d))
    t = torch.arange(T, device=x.device).float()
    ang = torch.einsum("t,f->tf", t, inv)
    cos, sin = ang.cos()[None, :, :], ang.sin()[None, :, :]
    x1, x2 = x[..., ::2], x[..., 1::2]
    out = torch.stack([x1 * cos - x2 * sin, x1 * sin + x2 * cos], -1)
    return out.flatten(-2)


def apply_plhe(x):
    # Phase-integrated helix over embedding novelty (Stage-0 candidate).
    # theta advances by omega estimated from detrended token-energy;
    # fused additively so RoPE fallback is a one-line config switch.
    B, T, d = x.shape
    with torch.no_grad():
        e = x.norm(dim=-1)                                   # [B, T]
        detr = e - e.mean(dim=1, keepdim=True)
        up = (detr[:, :-1] <= 0) & (detr[:, 1:] > 0)         # [B, T-1]
        period = T / up.float().sum(1).clamp(min=1)          # [B]
        omega = 2 * math.pi / period                         # [B]
        steps = torch.arange(T, device=x.device).float()
        theta = (omega.unsqueeze(1) * steps.unsqueeze(0)) % (2 * math.pi)
    carrier = torch.stack([theta.cos(), theta.sin()], -1)    # [B, T, 2]
    return x + 0.01 * carrier.repeat(1, 1, d // 2 + 1)[..., :d]


def count_report(cfg: Cfg):
    m = RoxChat(cfg)
    tot = m.n_params()
    act = m.active_per_token()
    n_moe = sum(1 for i in range(cfg.layers)
                if i % cfg.moe_every == cfg.moe_every - 1)
    return {"total_M": round(tot / 1e6, 1),
            "active_M": round(act / 1e6, 1),
            "active_frac": round(act / tot, 3),
            "moe_layers": n_moe}


if __name__ == "__main__":
    for name, c in (("500M", CFG_500M), ("1B", CFG_1B),
                    ("tiny", CFG_TINY)):
        print(name, count_report(c))
