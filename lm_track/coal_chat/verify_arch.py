"""Phase A gate: architecture v2 must pass before any training code.

Checks (CPU):
  1. Param counts in range for 360M / 500M configs
  2. Forward + backward on tiny config, no NaN
  3. Gradients flow to all major param groups (embeddings, attn, moe, norms)
  4. Emotion hooks active (limbic gate + emotion RoPE) and grad-connected
  5. MoE routing uses multiple experts (no collapse at init)
  6. Inference path (forward_last) runs without error

Exit 0 = gate passed.
"""
import sys
import os

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from arch_v2 import (CoalChatV2, CFG_TINY_V2, CFG_360M_V2, CFG_500M_V2)  # noqa: E402

FAILS = []


def check(name, cond, info=""):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name} {info}")
    if not cond:
        FAILS.append(name)


def param_counts():
    print("== param counts ==")
    for name, cfg, lo, hi in (("360M", CFG_360M_V2, 340e6, 400e6),
                              ("500M", CFG_500M_V2, 450e6, 550e6)):
        m = CoalChatV2(cfg)
        tot = m.n_params()
        act = m.active_per_token()
        check(f"{name}_count", lo <= tot <= hi,
              f"total={tot/1e6:.0f}M active={act/1e6:.0f}M")
        check(f"{name}_ratio", 0.2 <= act / tot <= 0.6,
              f"active_ratio={act/tot:.2f}")


def fwd_bwd():
    print("== forward/backward (tiny) ==")
    torch.manual_seed(0)
    m = CoalChatV2(CFG_TINY_V2)
    B, T = 2, 32
    idx = torch.randint(0, 256, (B, T))
    emo = torch.rand(B, 8)
    logits, aux, utils = m(idx, emotion=emo)
    check("logits_shape", logits.shape == (B, T, 256), str(tuple(logits.shape)))
    check("finite_forward", bool(torch.isfinite(logits).all()))
    loss = torch.nn.functional.cross_entropy(
        logits.reshape(-1, 256),
        torch.randint(0, 256, (B * T,)))
    loss = loss + 0.01 * aux if torch.is_tensor(aux) else loss
    loss.backward()
    # gradient flow
    groups = {"emb": 0, "attn": 0, "moe": 0, "norm": 0, "emotion": 0}
    for n, p in m.named_parameters():
        if p.grad is None:
            continue
        g = float(p.grad.abs().sum())
        # emotion hooks live under .attn. -> must match BEFORE attn
        if "limbic" in n or "emotion_rope" in n:
            groups["emotion"] += g
        elif "tok" in n:
            groups["emb"] += g
        elif "attn" in n or "q_proj" in n or "k_proj" in n or "v_proj" in n \
                or "o_proj" in n:
            groups["attn"] += g
        elif "ffn" in n or "gate" in n or "experts" in n or "shared" in n:
            groups["moe"] += g
        elif "ln" in n or "norm" in n:
            groups["norm"] += g
    for g, v in groups.items():
        check(f"grad_{g}", v > 0, f"sum={v:.3e}")
    check("no_nan_grad", all(torch.isfinite(p.grad).all()
                             for p in m.parameters() if p.grad is not None))


def moe_routing():
    print("== MoE routing (tiny) ==")
    torch.manual_seed(0)
    m = CoalChatV2(CFG_TINY_V2)
    idx = torch.randint(0, 256, (4, 64))
    _, _, utils = m(idx)
    flat = [u for layer in utils for u in layer]
    used = sum(1 for u in flat if u > 0)
    check("experts_used", used > 0, f"{used} expert-slots active")
    # not collapsed: at least 2 experts per MoE layer
    per_layer = []
    for layer in utils:
        per_layer.append(sum(1 for u in layer if u > 0))
    check("no_collapse", all(p >= 2 for p in per_layer),
          f"per-layer active experts={per_layer}")


def inference_path():
    print("== inference path (tiny) ==")
    torch.manual_seed(0)
    m = CoalChatV2(CFG_TINY_V2)
    m.eval()
    try:
        for b in m.blocks:
            b.reset_infer()
        ids = torch.randint(0, 256, (1, 8))
        # warm + step
        for _ in range(3):
            logits, S, reeval = m_forward_infer(m, ids)
        check("infer_runs", True)
        check("infer_finite", bool(torch.isfinite(logits).all()))
    except Exception as e:
        check("infer_runs", False, f"{type(e).__name__}: {e}")


def m_forward_infer(m, idx):
    """Minimal streaming step (no KV cache; recompute prefix)."""
    T = idx.shape[1]
    x = m.tok(idx)
    cos, sin = m._rope_cache(T, idx.device)
    mask = torch.triu(torch.ones(T, T, dtype=torch.bool), diagonal=1)
    S, reeval = [], 0
    for b in m.blocks:
        x, s, r = b.forward_last(x, cos, sin, mask, 0.0)
        S.append(s)
        reeval += r
    return m.head(m.ln(x))[0, -1], sum(S) / len(S), reeval


def main():
    print("PHASE A GATE: architecture v2\n")
    param_counts()
    fwd_bwd()
    moe_routing()
    inference_path()
    print()
    if FAILS:
        print(f"GATE FAILED: {FAILS}")
        return 1
    print("GATE PASSED: architecture v2 ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
