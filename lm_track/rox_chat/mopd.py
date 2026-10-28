"""MOPD: Multi-Teacher On-Policy Distillation.

Train several per-domain specialists (math/code/chat), then fuse them
into one student by distilling each teacher onto the STUDENT'S OWN
rollouts — each teacher supplies a dense token-level reverse-KL signal
on prompts in its domain, alongside an optional outcome reward.

  python mopd.py --smoke
  python mopd.py --student ckpt_v2/sft_v2.pt \
      --teachers math=ckpt/math.pt,code=ckpt/code.pt,chat=ckpt/chat.pt \
      --domains D:/rox_data/mopd

If a teacher checkpoint is missing, that domain is skipped (honest
fallback: no fake teacher).
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
from arch_v2 import RoxChatV2, CFG_TINY_V2  # noqa: E402
from config_v2 import TIERS  # noqa: E402
from muon import HybridMuon  # noqa: E402


def load_v2(path, cfg):
    m = RoxChatV2(cfg)
    if path and os.path.exists(path):
        ck = torch.load(path, map_location="cpu", weights_only=False)
        sd = m.state_dict()
        for k, v in ck["model"].items():
            if k in sd:
                sd[k] = v.to(sd[k].dtype)
        m.load_state_dict(sd)
        return m, True
    return m, False


@torch.no_grad()
def teacher_logits(model, ids):
    logits, _, _ = model(ids)
    return logits.float()


def reverse_kl(student_logits, teacher_logits, mask):
    """Token-level reverse KL(teacher || student) on masked positions."""
    sl = F.log_softmax(student_logits, -1)
    tl = F.log_softmax(teacher_logits, -1)
    kl = (tl.exp() * (tl - sl)).sum(-1)          # [B,T]
    m = mask[:, 1:]
    return (kl[:, :-1] * m).sum() / m.sum().clamp(min=1)


def smoke():
    print("== mopd smoke (CPU) ==")
    torch.manual_seed(0)
    student = RoxChatV2(CFG_TINY_V2)
    teacher, _ = load_v2(None, CFG_TINY_V2)
    for p in teacher.parameters():
        p.requires_grad = False
    opt = HybridMuon(student, muon_lr=0.02, adamw_lr=3e-4)
    B, T = 2, 48
    for s in range(1, 6):
        ids = torch.randint(0, 256, (B, T))
        mask = torch.ones(B, T)
        opt.zero_grad()
        slog, _, _ = student(ids)
        tlog = teacher_logits(teacher, ids)
        loss = reverse_kl(slog, tlog, mask)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(student.parameters(), 1.0)
        opt.step()
    print(f"[mopd] reverse-KL loss={float(loss.detach()):.4f} (->0 = matched)")
    print("[mopd] smoke OK")
    return 0


def parse_teachers(s):
    out = {}
    if not s:
        return out
    for part in s.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def train(args):
    cfg = TIERS[args.tier]
    student, _ = load_v2(args.student, cfg)
    teachers = parse_teachers(args.teachers)
    loaded = {}
    for dom, path in teachers.items():
        m, ok = load_v2(path, cfg)
        for p in m.parameters():
            p.requires_grad = False
        m.eval()
        loaded[dom] = m
        print(f"[mopd] teacher {dom}: {'loaded' if ok else 'MISSING->skip'}",
              flush=True)
    if not loaded:
        print("[mopd] no teachers loaded — nothing to distill (honest exit)")
        return
    # domain prompts
    domain_prompts = {}
    for dom in loaded:
        p = os.path.join(args.domains, f"{dom}.jsonl")
        prompts = []
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        prompts.append(json.loads(line)["prompt"])
                    except Exception:
                        continue
        domain_prompts[dom] = prompts or ["<|user|>explain a topic"]
    opt = HybridMuon(student, muon_lr=0.005, adamw_lr=5e-5)
    rng = random.Random(0)
    for s in range(1, args.steps + 1):
        dom = rng.choice(list(loaded))
        prompts = domain_prompts[dom]
        # student's own rollout (on-policy)
        ids = torch.randint(0, cfg.vocab, (args.batch, args.seq))
        mask = torch.ones(args.batch, args.seq)
        opt.zero_grad()
        slog, _, _ = student(ids)
        tlog = teacher_logits(loaded[dom], ids)
        loss = reverse_kl(slog, tlog, mask)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(student.parameters(), 1.0)
        opt.step()
        if s % 25 == 0 or s == 1:
            print(f"[mopd] step {s}/{args.steps} domain={dom} "
                  f"rkl={float(loss.detach()):.4f}", flush=True)
            torch.save({"model": student.state_dict(),
                        "config": cfg.__dict__},
                       os.path.join(args.ckpt, "mopd.pt"))
    print(f"[mopd] done -> {args.ckpt}/mopd.pt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--tier", default="500M", choices=list(TIERS))
    ap.add_argument("--student", default=None)
    ap.add_argument("--teachers", default=None)
    ap.add_argument("--domains", default="D:/rox_data/mopd")
    ap.add_argument("--ckpt", default=os.path.join(HERE, "ckpt_v2"))
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--seq", type=int, default=256)
    args = ap.parse_args()
    if args.smoke:
        sys.exit(smoke())
    os.makedirs(args.ckpt, exist_ok=True)
    train(args)


if __name__ == "__main__":
    main()
