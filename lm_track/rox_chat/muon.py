"""Muon optimizer (Liu et al. 2025) + AdamW hybrid.

Muon orthogonalizes the momentum update via Newton-Schulz iteration and
matches AdamW's update RMS, claiming ~2x compute efficiency. Used on 2D
hidden matrices (attn/ffn/expert weights); AdamW handles embeddings,
norms, biases, gates and the (1D) gate_bias.

Usage:
    groups = split_params(model)
    opt = HybridMuon(groups, muon_lr=0.02, adamw_lr=3e-4)
    opt.step(); opt.zero_grad()
"""
import torch


def zeropower_via_newtonschulz5(g, steps=5, eps=1e-7):
    """Approximate the orthogonal factor of g via Newton-Schulz."""
    assert g.ndim >= 2
    a, b, c = (3.4445, -4.7750, 2.0315)
    x = g.to(torch.bfloat16)
    transposed = x.size(0) > x.size(1)
    if transposed:
        x = x.T
    x = x / (x.norm() + eps)
    for _ in range(steps):
        aa = x @ x.T
        bb = b * aa + c * (aa @ aa)
        x = a * x + bb @ x
    if transposed:
        x = x.T
    return x.to(g.dtype)


class Muon(torch.optim.Optimizer):
    def __init__(self, params, lr=0.02, momentum=0.95, nesterov=True,
                 ns_steps=5, weight_decay=0.0):
        defaults = dict(lr=lr, momentum=momentum, nesterov=nesterov,
                        ns_steps=ns_steps, weight_decay=weight_decay)
        super().__init__(params, defaults)

    @torch.no_grad()
    def step(self, closure=None):
        loss = None
        if closure is not None:
            with torch.enable_grad():
                loss = closure()
        for group in self.param_groups:
            for p in group["params"]:
                if p.grad is None:
                    continue
                g = p.grad
                if g.ndim < 2:
                    raise ValueError("Muon only accepts >=2D params; "
                                     "route 1D params to AdamW")
                state = self.state[p]
                if "buf" not in state:
                    state["buf"] = torch.zeros_like(g)
                buf = state["buf"]
                buf.mul_(group["momentum"]).add_(g)
                if group["nesterov"]:
                    g = g.add(buf, alpha=group["momentum"])
                else:
                    g = buf
                o = zeropower_via_newtonschulz5(g, group["ns_steps"])
                scale = max(1.0, o.size(0) / o.size(1)) ** 0.5
                if group["weight_decay"] > 0:
                    p.data.mul_(1 - group["lr"] * group["weight_decay"])
                p.data.add_(o, alpha=-group["lr"] * scale)
        return loss


def split_params(model, muon_name_hints=("q_proj", "k_proj", "v_proj",
                                         "o_proj", "w1", "w2", "w3",
                                         "experts", "shared")):
    """Return (muon_params, adamw_params).

    Muon: 2D matrices whose names match the hints (hidden transforms).
    AdamW: everything else (embeddings, norms, gates, biases, 1D params).
    """
    muon, adamw = [], []
    for n, p in model.named_parameters():
        if not p.requires_grad:
            continue
        is_matrix = p.ndim >= 2
        hinted = any(h in n for h in muon_name_hints)
        # gate weight is intentionally AdamW (routing stability)
        if is_matrix and hinted and "gate" not in n:
            muon.append(p)
        else:
            adamw.append(p)
    return muon, adamw


class HybridMuon:
    """Convenience wrapper holding a Muon + an AdamW optimizer."""

    def __init__(self, model, muon_lr=0.02, adamw_lr=3e-4,
                 momentum=0.95, weight_decay=0.1, betas=(0.9, 0.95)):
        muon_p, adamw_p = split_params(model)
        self.muon = Muon(muon_p, lr=muon_lr, momentum=momentum,
                         weight_decay=0.0)
        self.adamw = torch.optim.AdamW(adamw_p, lr=adamw_lr, betas=betas,
                                       weight_decay=weight_decay)
        self.n_muon = sum(p.numel() for p in muon_p)
        self.n_adamw = sum(p.numel() for p in adamw_p)

    def zero_grad(self, set_to_none=True):
        self.muon.zero_grad(set_to_none=set_to_none)
        self.adamw.zero_grad(set_to_none=set_to_none)

    def step(self):
        self.muon.step()
        self.adamw.step()

    def set_lr(self, muon_lr=None, adamw_lr=None):
        if muon_lr is not None:
            for g in self.muon.param_groups:
                g["lr"] = muon_lr
        if adamw_lr is not None:
            for g in self.adamw.param_groups:
                g["lr"] = adamw_lr

    def state_dict(self):
        return {"muon": self.muon.state_dict(),
                "adamw": self.adamw.state_dict()}

    def load_state_dict(self, sd):
        try:
            self.muon.load_state_dict(sd["muon"])
            self.adamw.load_state_dict(sd["adamw"])
        except Exception:
            pass

    def report(self):
        return (f"muon={self.n_muon/1e6:.1f}M params "
                f"adamw={self.n_adamw/1e6:.1f}M params")


if __name__ == "__main__":
    # smoke: 2D matrix via Muon + 1D bias via AdamW, one step, no NaN
    torch.manual_seed(0)

    class Tiny(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.q_proj = torch.nn.Linear(8, 16, bias=True)

    m = Tiny()
    opt = HybridMuon(m, muon_lr=0.02, adamw_lr=3e-4)
    x = torch.randn(4, 8)
    loss = (m.q_proj(x) ** 2).mean()
    loss.backward()
    opt.step()
    ok = all(torch.isfinite(p).all() for p in m.parameters())
    print(f"[muon] smoke: finite={bool(ok)} {opt.report()}")
    raise SystemExit(0 if ok else 1)
