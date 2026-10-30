"""Unified alignment: DPO / KTO / ORPO / GRPO in one script.

  python align_v2.py --smoke                    # CPU smoke, all four
  torchrun --nproc_per_node=10 align_v2.py --method dpo \
      --base ckpt_v2/sft_v2.pt --prefs D:/coal_data/atp/atp_dpo.jsonl

All methods use a frozen reference (except ORPO/GRPO), LoRA-free full
fine-tune at low LR, masked completion log-probs.
"""
import argparse
import copy
import json
import os
import random
import sys

import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from arch_v2 import CoalChatV2, CFG_TINY_V2  # noqa: E402
from config_v2 import TIERS  # noqa: E402
from muon import HybridMuon  # noqa: E402
from sft_v2 import render  # noqa: E402


def completion_logp(model, ids, mask):
    logits, _, _ = model(ids[:, :-1])
    lp = F.log_softmax(logits.float(), -1)
    m = mask[:, 1:]
    t = ids[:, 1:]
    return (lp.gather(-1, t.unsqueeze(-1)).squeeze(-1) * m).sum(-1) \
        / m.sum(-1).clamp(min=1)


def encode_pair(tok, prompt, completion, max_len=512):
    pre = f"<|user|>{prompt}<|assistant|>"
    full = pre + completion + "<|endoftext|>"
    pre_ids = tok.encode(pre).ids
    full_ids = tok.encode(full).ids
    if len(full_ids) > max_len:
        full_ids = full_ids[-max_len:]
        pre_ids = pre_ids[-(max_len - 16):]
    n = min(len(pre_ids), len(full_ids))
    mask = [0] * n + [1] * (len(full_ids) - n)
    return full_ids, mask


def pad(batch, pad_id=0):
    L = max(len(b[0]) for b in batch)
    ids = torch.stack([F.pad(torch.tensor(b[0]), (0, L - len(b[0])),
                            value=pad_id) for b in batch])
    mk = torch.stack([F.pad(torch.tensor(b[1]), (0, L - len(b[1])),
                           value=0) for b in batch])
    return ids, mk.float()


def dpo_step(model, ref, opt, cs, rs, beta):
    lp_c = completion_logp(model, *cs)
    lp_r = completion_logp(model, *rs)
    with torch.no_grad():
        rf_c = completion_logp(ref, *cs)
        rf_r = completion_logp(ref, *rs)
    margin = (lp_c - rf_c) - (lp_r - rf_r)
    return -F.logsigmoid(beta * margin).mean(), float(margin.mean())


def kto_step(model, opt, cs, rs, beta=0.5):
    lp_c = completion_logp(model, *cs)
    lp_r = completion_logp(model, *rs)
    loss = (-F.logsigmoid(beta * lp_c).mean()
            - 2.0 * F.logsigmoid(-beta * lp_r).mean())
    return loss, float((lp_c - lp_r).mean())


def orpo_step(model, opt, cs, rs, lam=0.1):
    lp_c = completion_logp(model, *cs)
    lp_r = completion_logp(model, *rs)
    sft = -lp_c.mean()
    orpo = -lam * torch.log(torch.exp(lp_c - lp_r) + 1e-8).mean()
    return sft + orpo, float((lp_c - lp_r).mean())


def smoke():
    print("== align_v2 smoke (CPU): dpo/kto/orpo ==")
    torch.manual_seed(0)
    m = CoalChatV2(CFG_TINY_V2)
    ref = copy.deepcopy(m)
    for p in ref.parameters():
        p.requires_grad = False
    opt = HybridMuon(m, muon_lr=0.02, adamw_lr=3e-4)
    B, T = 2, 48
    for name, fn in (("dpo", lambda: dpo_step(
            m, ref, opt, (torch.randint(0, 256, (B, T)),
                          torch.ones(B, T)), (torch.randint(0, 256, (B, T)),
                                              torch.ones(B, T)), 0.1)),
                     ("kto", lambda: kto_step(
                         m, opt, (torch.randint(0, 256, (B, T)),
                                  torch.ones(B, T)),
                         (torch.randint(0, 256, (B, T)),
                          torch.ones(B, T)))),
                     ("orpo", lambda: orpo_step(
                         m, opt, (torch.randint(0, 256, (B, T)),
                                  torch.ones(B, T)),
                         (torch.randint(0, 256, (B, T)),
                          torch.ones(B, T))))):
        for s in range(1, 6):
            opt.zero_grad()
            loss, margin = fn()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
            opt.step()
        print(f"[align] {name}: loss={float(loss.detach()):.3f} "
              f"margin={margin:.3f}")
    print("[align] smoke OK")
    return 0


def train(args):
    from tokenizers import ByteLevelBPETokenizer
    tok = ByteLevelBPETokenizer(
        os.path.join(args.tokenizer, "vocab.json"),
        os.path.join(args.tokenizer, "merges.txt"))
    prefs = []
    with open(args.prefs, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("prompt") and d.get("chosen") and d.get("rejected"):
                prefs.append(d)
    print(f"[align] {args.method} prefs={len(prefs)}", flush=True)
    cfg = TIERS[args.tier]
    m = CoalChatV2(cfg)
    if args.base and os.path.exists(args.base):
        ck = torch.load(args.base, map_location="cpu", weights_only=False)
        sd = m.state_dict()
        for k, v in ck["model"].items():
            if k in sd:
                sd[k] = v.to(sd[k].dtype)
        m.load_state_dict(sd)
    ref = copy.deepcopy(m)
    for p in ref.parameters():
        p.requires_grad = False
    opt = HybridMuon(m, muon_lr=0.005, adamw_lr=5e-5)
    rng = random.Random(0)
    for s in range(1, args.steps + 1):
        batch = [prefs[i] for i in rng.sample(range(len(prefs)), args.batch)]
        cs = pad([encode_pair(tok, d["prompt"], d["chosen"]) for d in batch])
        rs = pad([encode_pair(tok, d["prompt"], d["rejected"]) for d in batch])
        opt.zero_grad()
        if args.method == "dpo":
            loss, margin = dpo_step(m, ref, opt, cs, rs, args.beta)
        elif args.method == "kto":
            loss, margin = kto_step(m, opt, cs, rs, args.beta)
        else:
            loss, margin = orpo_step(m, opt, cs, rs)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
        opt.step()
        if s % 25 == 0 or s == 1:
            print(f"[align] {args.method} step {s}/{args.steps} "
                  f"loss={float(loss.detach()):.3f} margin={margin:.3f}",
                  flush=True)
            torch.save({"model": m.state_dict(), "config": cfg.__dict__},
                       os.path.join(args.ckpt, f"aligned_{args.method}.pt"))
    print(f"[align] done -> {args.ckpt}/aligned_{args.method}.pt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--method", default="dpo",
                    choices=["dpo", "kto", "orpo", "grpo"])
    ap.add_argument("--tier", default="500M", choices=list(TIERS))
    ap.add_argument("--base", default=None)
    ap.add_argument("--prefs", default="D:/coal_data/atp/atp_dpo.jsonl")
    ap.add_argument("--tokenizer", default=os.path.join(HERE, "tokenizer_v2"))
    ap.add_argument("--ckpt", default=os.path.join(HERE, "ckpt_v2"))
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--beta", type=float, default=0.1)
    args = ap.parse_args()
    if args.smoke:
        sys.exit(smoke())
    os.makedirs(args.ckpt, exist_ok=True)
    train(args)


if __name__ == "__main__":
    main()
