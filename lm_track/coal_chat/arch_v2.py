"""Coal-Chat V2 architecture: modern small-MoE recipe + Coal mechanisms.

Adds to arch.py (backward compatible; arch.py untouched):
  - RMSNorm (pre-norm)
  - GQA (grouped-query attention, decoupled head dim)
  - per-head QK-norm (biggest single lever per HobbyLM ablation)
  - YaRN RoPE scaling (context extension 4K -> 8K+)
  - sigmoid gating + bias-based load balancing (DeepSeek-V3 style)
  - shared expert (always-on) alongside routed experts
  - emotion hooks: limbic-routed attention gate + emotion-conditioned RoPE
    (trained paths: limbic gate, emotion RoPE; gradient-decay signal and
     consensus reward are surfaced for the training loop to consume)

Reuses from arch.py: FOUFFN (FOU surprise-gated experts), apply_plhe.
"""
import math
from dataclasses import dataclass, field

import torch
import torch.nn as nn
import torch.nn.functional as F

from arch import FOUFFN, apply_plhe  # noqa: E402


# ---------------------------------------------------------------------------
# Norm
# ---------------------------------------------------------------------------
class RMSNorm(nn.Module):
    def __init__(self, d, eps=1e-5):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(d))
        self.eps = eps

    def forward(self, x):
        dt = x.dtype
        xf = x.float()
        n = xf * torch.rsqrt(xf.pow(2).mean(-1, keepdim=True) + self.eps)
        return (n * self.weight.float()).to(dt)


# ---------------------------------------------------------------------------
# RoPE (+ YaRN)
# ---------------------------------------------------------------------------
def build_rope(T, head_dim, base, device, yarn_scale=None):
    """Returns (cos, sin) each [T, head_dim/2]. YaRN scales the low
    frequencies by 1/scale with a linear ramp (context extension)."""
    inv = 1.0 / (base ** (torch.arange(0, head_dim, 2,
                                       device=device).float() / head_dim))
    if yarn_scale is not None and yarn_scale > 1.0:
        # ramp: low freq dims scaled, high freq untouched
        ramp = torch.linspace(0, 1, inv.numel(), device=device)
        inv = inv * (1.0 - ramp) + (inv / yarn_scale) * ramp
    t = torch.arange(T, device=device).float()
    ang = torch.outer(t, inv)                      # [T, hd/2]
    return ang.cos(), ang.sin()


def apply_rope(x, cos, sin):
    """x: [B, H, T, hd]; cos/sin: [T, hd/2]."""
    x1, x2 = x[..., ::2], x[..., 1::2]
    c = cos[None, None, :, :]
    s = sin[None, None, :, :]
    out = torch.stack([x1 * c - x2 * s, x1 * s + x2 * c], -1)
    return out.flatten(-2)


# ---------------------------------------------------------------------------
# Emotion hooks (trained)
# ---------------------------------------------------------------------------
class LimbicGate(nn.Module):
    """emotional-state vector -> per-head attention gate in (0.1, 2.0)."""

    def __init__(self, n_heads, emotion_dim=8, hidden=32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(emotion_dim, hidden), nn.SiLU(),
            nn.Linear(hidden, n_heads))
        nn.init.normal_(self.net[-1].weight, std=0.02)
        nn.init.zeros_(self.net[-1].bias)

    def forward(self, e):
        return 0.1 + 1.9 * torch.sigmoid(self.net(e))   # [B, H]


class EmotionRoPE(nn.Module):
    """arousal -> per-head RoPE frequency scale (emotion-conditioned RoPE)."""

    def __init__(self, n_heads):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(1, 16), nn.SiLU(),
                                 nn.Linear(16, n_heads))
        nn.init.zeros_(self.net[-1].weight)
        nn.init.zeros_(self.net[-1].bias)

    def forward(self, arousal):
        return 1.0 + 0.5 * torch.tanh(self.net(arousal))  # [B, H] in (0.5,1.5)


# ---------------------------------------------------------------------------
# GQA attention with QK-norm
# ---------------------------------------------------------------------------
class GQAttention(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.hq = cfg.heads
        self.hkv = cfg.n_kv_heads
        self.hd = cfg.head_dim
        self.scale = self.hd ** -0.5
        d = cfg.d
        self.q_proj = nn.Linear(d, self.hq * self.hd, bias=False)
        self.k_proj = nn.Linear(d, self.hkv * self.hd, bias=False)
        self.v_proj = nn.Linear(d, self.hkv * self.hd, bias=False)
        self.o_proj = nn.Linear(self.hq * self.hd, d, bias=False)
        self.qk_norm = cfg.qk_norm
        if self.qk_norm:
            self.q_norm = RMSNorm(self.hd)
            self.k_norm = RMSNorm(self.hd)
        self.limbic = LimbicGate(self.hq) if cfg.emotion else None
        self.emotion_rope = EmotionRoPE(self.hq) if cfg.emotion else None

    def forward(self, x, cos, sin, mask, emotion=None):
        B, T, _ = x.shape
        q = self.q_proj(x).view(B, T, self.hq, self.hd).transpose(1, 2)
        k = self.k_proj(x).view(B, T, self.hkv, self.hd).transpose(1, 2)
        v = self.v_proj(x).view(B, T, self.hkv, self.hd).transpose(1, 2)
        if self.qk_norm:
            q = self.q_norm(q)
            k = self.k_norm(k)
        # emotion-conditioned RoPE: per-head freq scale
        if self.emotion_rope is not None and emotion is not None:
            scale = self.emotion_rope(emotion[:, 1:2])      # [B, Hq]
            q = q * scale[:, :, None, None]
            k = k * scale[:, :self.hkv, None, None]
        q = apply_rope(q, cos, sin)
        k = apply_rope(k, cos, sin)
        # limbic per-head gate
        if self.limbic is not None and emotion is not None:
            g = self.limbic(emotion)                         # [B, Hq]
            q = q * g[:, :, None, None]
        # GQA expand kv
        if self.hkv != self.hq:
            rep = self.hq // self.hkv
            k = k.repeat_interleave(rep, dim=1)
            v = v.repeat_interleave(rep, dim=1)
        att = (q @ k.transpose(-2, -1)) * self.scale
        att = att.masked_fill(mask[None, None, :, :], float("-inf"))
        att = F.softmax(att.float(), dim=-1).to(q.dtype)
        out = (att @ v).transpose(1, 2).reshape(B, T, self.hq * self.hd)
        return self.o_proj(out)


# ---------------------------------------------------------------------------
# MoE v2: routed experts + shared expert, sigmoid gating, bias balancing
# ---------------------------------------------------------------------------
class EMEv2(nn.Module):
    """FOU experts with DeepSeek-V3-style routing.

    Train: sigmoid gating, top-k, bias-based balancing (bias updated by
    the training loop via update_balance_bias, not by gradient).
    Infer: EME hysteresis (incumbent bonus + surprise-forced re-eval).
    """

    def __init__(self, cfg, governor=None, layer_id=0):
        super().__init__()
        h = int(cfg.d * cfg.expert_mult)   # fine-grained expert width
        self.cfg = cfg
        self.experts = nn.ModuleList(FOUFFN(cfg.d, h)
                                     for _ in range(cfg.experts))
        self.shared = FOUFFN(cfg.d, h)          # always-on
        self.gate = nn.Linear(cfg.d, cfg.experts, bias=False)
        self.gate_bias = nn.Parameter(torch.zeros(cfg.experts),
                                      requires_grad=False)
        self.governor = governor
        self.layer_id = layer_id
        self.prev = None
        self.last_util = None

    def reset_infer(self):
        for e in self.experts:
            e.reset_cache()
        self.shared.reset_cache()
        self.prev = None

    @torch.no_grad()
    def update_balance_bias(self, lr=1e-3):
        """DeepSeek-V3 aux-loss-free balancing: nudge bias toward uniform."""
        if self.last_util is None:
            return
        target = 1.0 / self.cfg.experts
        self.gate_bias += lr * (target - self.last_util)

    def forward(self, x, infer=False, surprise=None):
        if infer:
            return self._infer(x, surprise)
        scores = torch.sigmoid(self.gate(x) + self.gate_bias)  # [B,T,E]
        topw, topi = torch.topk(scores, self.cfg.topk, dim=-1)
        topw = topw / topw.sum(-1, keepdim=True).clamp(min=1e-6)
        outs = torch.stack([e(x) for e in self.experts], dim=-2)  # [B,T,E,d]
        w = torch.zeros_like(scores).scatter_(-1, topi, topw)     # [B,T,E]
        routed = (w.unsqueeze(-1) * outs).sum(-2)
        shared = self.shared(x)
        self.last_util = (topi.reshape(-1)
                          .bincount(minlength=self.cfg.experts)
                          .float() / topi.numel()).detach()
        util = self.last_util.tolist()
        # balance aux kept small; primary balancing is the bias update
        balance = self.last_util.pow(2).sum() * self.cfg.experts
        return routed + shared, balance, util

    @torch.no_grad()
    def _infer(self, x, surprise):
        lam = self.cfg.eme_lambda
        if self.governor is not None:
            lam = self.governor.query(self.layer_id)
        scores = torch.sigmoid(self.gate(x) + self.gate_bias)
        if lam is not None and self.prev is not None \
                and surprise is not None and surprise <= 0:
            out, _ = self.experts[self.prev].step(x)
            return out + self.shared.step(x)[0], self.prev, False, 0.0
        if lam is not None and self.prev is not None:
            scores[self.prev] += lam
        topw, topi = torch.topk(scores, self.cfg.topk)
        topw = topw / topw.sum().clamp(min=1e-6)
        out = torch.zeros_like(x)
        smin = 1e9
        for k in range(self.cfg.topk):
            o, s = self.experts[int(topi[k])].step(x)
            out = out + float(topw[k]) * o
            smin = min(smin, s)
        o, _ = self.shared.step(x)
        self.prev = int(topi[0])
        return out + o, self.prev, True, smin

    def forward_last(self, f, s_minus_thr):
        out = torch.zeros_like(f)
        o, e, r, s = self._infer(f[-1], s_minus_thr)
        out[-1] = o
        return out, e, r, s


# ---------------------------------------------------------------------------
# Block v2
# ---------------------------------------------------------------------------
class BlockV2(nn.Module):
    def __init__(self, cfg, moe, governor=None, layer_id=0):
        super().__init__()
        self.cfg = cfg
        self.ln1 = RMSNorm(cfg.d)
        self.ln2 = RMSNorm(cfg.d)
        self.attn = GQAttention(cfg)
        self.moe = moe
        h = int(cfg.d * cfg.ffn_mult)
        self.ffn = EMEv2(cfg, governor, layer_id) if moe else FOUFFN(cfg.d, h)

    def reset_infer(self):
        if self.moe:
            self.ffn.reset_infer()
        else:
            self.ffn.reset_cache()

    def forward(self, x, cos, sin, mask, emotion=None, sink=None):
        a = self.attn(self.ln1(x), cos, sin, mask, emotion)
        x = x + a
        h = self.ln2(x)
        if self.moe:
            out, balance, util = self.ffn(h)
            if sink is not None:
                sink["balance"] = sink.get("balance", 0.0) + balance
                sink.setdefault("util", []).append(util)
            return x + out, balance, util
        imp = torch.sigmoid(h.mean(-1))
        out = self.ffn(h)
        sparse_aux = imp.mean()
        if sink is not None:
            sink["sparse"] = sink.get("sparse", 0.0) + sparse_aux
        return x + out * imp.unsqueeze(-1), sparse_aux, None

    @torch.no_grad()
    def forward_last(self, x, cos, sin, mask, s_minus_thr):
        a = self.attn(self.ln1(x), cos, sin, mask)
        x = x + a
        h = self.ln2(x)
        if self.moe:
            out, e, r, s = self.ffn.forward_last(h[0], s_minus_thr)
            return x + out.unsqueeze(0), s, int(r)
        out = torch.zeros_like(h)
        o, s = self.ffn.step(h[0, -1])
        out[0, -1] = o
        return x + out, s, 0


# ---------------------------------------------------------------------------
# Full model
# ---------------------------------------------------------------------------
class CoalChatV2(nn.Module):
    def __init__(self, cfg, governor=None):
        super().__init__()
        self.cfg = cfg
        self.tok = nn.Embedding(cfg.vocab, cfg.d)
        self.blocks = nn.ModuleList(
            BlockV2(cfg, moe=(i % cfg.moe_every == cfg.moe_every - 1),
                    governor=governor, layer_id=i)
            for i in range(cfg.layers))
        self.governor = governor
        self.ln = RMSNorm(cfg.d)
        self.head = nn.Linear(cfg.d, cfg.vocab, bias=False)
        self.apply(self._init)
        self._rope = None
        self._rope_T = 0

    @staticmethod
    def _init(m):
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, std=0.02)

    def _rope_cache(self, T, device):
        if self._rope is None or self._rope_T < T or \
                self._rope[0].device != device:
            self._rope = build_rope(T, self.cfg.head_dim, self.cfg.rope_base,
                                    device, self.cfg.yarn_scale)
            self._rope_T = T
        return self._rope

    def n_params(self):
        return sum(p.numel() for p in self.parameters())

    def active_per_token(self):
        c = self.cfg
        he = int(c.d * c.expert_mult)
        hd = int(c.d * c.ffn_mult)
        per_expert = 3 * c.d * he
        dense_ffn = 3 * c.d * hd
        attn = (c.heads * c.head_dim + 2 * c.n_kv_heads * c.head_dim
                + c.heads * c.head_dim) * c.d
        n_moe = sum(1 for i in range(c.layers)
                    if i % c.moe_every == c.moe_every - 1)
        n_dense = c.layers - n_moe
        per_tok = c.layers * attn + n_dense * dense_ffn \
            + n_moe * (c.topk + 1) * per_expert
        return per_tok

    def forward(self, idx, emotion=None):
        B, T = idx.shape
        x = self.tok(idx)
        if self.cfg.position == "plhe":
            x = apply_plhe(x)
        cos, sin = self._rope_cache(T, idx.device)
        mask = torch.triu(torch.ones(T, T, dtype=torch.bool,
                                     device=idx.device), diagonal=1)
        if emotion is not None:
            emotion = emotion.to(x.dtype)
        aux, utils, sink = 0.0, [], {}
        for b in self.blocks:
            x, a, u = b(x, cos, sin, mask, emotion, sink=sink)
            aux = aux + a
            if u is not None:
                utils.append(u)
        logits = self.head(self.ln(x))
        return logits, aux, utils

    def forward_parts(self, idx, emotion=None):
        B, T = idx.shape
        x = self.tok(idx)
        if self.cfg.position == "plhe":
            x = apply_plhe(x)
        cos, sin = self._rope_cache(T, idx.device)
        mask = torch.triu(torch.ones(T, T, dtype=torch.bool,
                                     device=idx.device), diagonal=1)
        if emotion is not None:
            emotion = emotion.to(x.dtype)
        sink, utils = {}, []
        for b in self.blocks:
            x, _, u = b(x, cos, sin, mask, emotion, sink=sink)
            if u is not None:
                utils.append(u)
        parts = {"balance": sink.get("balance", torch.tensor(0.0)),
                 "sparse": sink.get("sparse", torch.tensor(0.0))}
        return self.head(self.ln(x)), parts, utils

    def update_balance_bias(self, lr=1e-3):
        for b in self.blocks:
            if b.moe:
                b.ffn.update_balance_bias(lr)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CfgV2:
    layers: int = 16
    d: int = 768
    heads: int = 12
    n_kv_heads: int = 3
    head_dim: int = 64
    ffn_mult: float = 2.75
    expert_mult: float = 0.45       # expert width = d * expert_mult
    experts: int = 36
    topk: int = 6
    moe_every: int = 2
    vocab: int = 50304
    ctx: int = 4096
    position: str = "rope"
    qk_norm: bool = True
    rope_base: float = 10000.0
    yarn_scale: float = 1.0
    emotion: bool = True
    eme_lambda: float = 2.0
    fou_topk_frac: float = 0.25
    tie_embeddings: bool = True


CFG_360M_V2 = CfgV2(layers=16, d=768, heads=12, n_kv_heads=3, head_dim=64,
                    experts=40, topk=6, moe_every=2, expert_mult=0.4)
CFG_500M_V2 = CfgV2(layers=18, d=896, heads=14, n_kv_heads=4, head_dim=64,
                    experts=36, topk=6, moe_every=2, expert_mult=0.4)
CFG_TINY_V2 = CfgV2(layers=4, d=128, heads=4, n_kv_heads=2, head_dim=32,
                    experts=8, topk=2, moe_every=2, vocab=256, ctx=128,
                    expert_mult=1.0)


if __name__ == "__main__":
    for name, c in (("360M", CFG_360M_V2), ("500M", CFG_500M_V2),
                    ("tiny", CFG_TINY_V2)):
        m = CoalChatV2(c)
        tot = m.n_params()
        act = m.active_per_token()
        print(f"{name}: total={tot/1e6:.1f}M active={act/1e6:.1f}M "
              f"ratio={act/tot:.2f}")
