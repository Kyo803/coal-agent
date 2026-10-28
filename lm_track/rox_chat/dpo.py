"""DPO alignment pass (cheapest preference method): learn pushback and
fallback behaviors from (prompt, chosen, rejected) triples — including
explicit retrieval-miss -> honest-uncertainty and leading-question ->
pushback examples (resilience ATP requirement). cpu_test() on toy data.
"""
import torch
import torch.nn.functional as F


def seq_logp(model, ids):
    logits, _, _ = model(ids[:, :-1])
    lp = F.log_softmax(logits, -1)
    return lp.gather(-1, ids[:, 1:].unsqueeze(-1)).squeeze(-1).sum(-1)


def dpo_step(model, ref, opt, prompt, chosen, rejected, beta=0.1):
    """All inputs [B,T] full sequences (prompt+completion)."""
    model.train()
    opt.zero_grad()
    lp_c = seq_logp(model, chosen)
    lp_r = seq_logp(model, rejected)
    with torch.no_grad():
        rf_c = seq_logp(ref, chosen)
        rf_r = seq_logp(ref, rejected)
    loss = -F.logsigmoid(beta * ((lp_c - rf_c) - (lp_r - rf_r))).mean()
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    opt.step()
    return float(loss.detach())


def cpu_test():
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from arch import RoxChat, CFG_TINY
    import copy
    torch.manual_seed(0)
    m = RoxChat(CFG_TINY)
    ref = copy.deepcopy(m)
    opt = torch.optim.AdamW(m.parameters(), lr=1e-4)
    B, T = 2, 24
    p = torch.randint(0, 256, (B, T))
    c = torch.randint(0, 256, (B, T))
    rj = torch.randint(0, 256, (B, T))
    l0 = dpo_step(m, ref, opt, p, c, rj)
    l1 = dpo_step(m, ref, opt, p, c, rj)
    print(f"[dpo] cpu_test loss {l0:.3f} -> {l1:.3f}")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if cpu_test() else 1)
