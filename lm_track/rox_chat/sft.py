"""Masked SFT: loss on assistant tokens only. Generic over any
[(prompt_ids, full_ids)] pairs; cpu_test() proves the loop on toy data.
Production feeds llm_500m's 896K mined pairs through this exact function.
"""
import torch
import torch.nn.functional as F


def sft_step(model, opt, ids_batch, mask_batch):
    """ids: [B,T] full sequence; mask: [B,T] bool (True = learn here)."""
    model.train()
    opt.zero_grad()
    logits, aux, _ = model(ids_batch[:, :-1])
    lb = mask_batch[:, 1:]
    tb = ids_batch[:, 1:]
    loss = F.cross_entropy(logits[lb], tb[lb]) + 0.01 * aux
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    opt.step()
    return float(loss.detach())


def cpu_test():
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from arch import RoxChat, CFG_TINY
    torch.manual_seed(0)
    m = RoxChat(CFG_TINY)
    opt = torch.optim.AdamW(m.parameters(), lr=3e-4)
    B, T = 4, 32
    ids = torch.randint(0, 256, (B, T))
    mask = torch.zeros(B, T, dtype=torch.bool)
    mask[:, T // 2:] = True
    l0 = sft_step(m, opt, ids, mask)
    l1 = sft_step(m, opt, ids, mask)
    print(f"[sft] cpu_test loss {l0:.3f} -> {l1:.3f} "
          f"({'OK' if l1 < l0 else 'FAIL'})")
    return l1 < l0


if __name__ == "__main__":
    raise SystemExit(0 if cpu_test() else 1)
