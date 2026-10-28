"""Train the tiny GPT on raw stories.  python train.py [--steps N]
Logs train/val loss + a generated sample every 200 steps. Checkpoint: rox0.pt
"""
import os
import sys
import time

import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from model_gpt import TinyGPT, sample  # noqa: E402
from data_tinystories import load  # noqa: E402

STEPS = 1200
BATCH = 12
CTX = 128
LR = 3e-4


def batch_of(data, n, ctx):
    i = torch.randint(0, len(data) - ctx - 1, (n,))
    x = torch.stack([data[j:j + ctx] for j in i])
    y = torch.stack([data[j + 1:j + ctx + 1] for j in i])
    return x, y


def main():
    steps = STEPS
    resume = False
    for a in sys.argv[1:]:
        if a.startswith("--steps="):
            steps = int(a.split("=")[1])
        if a == "--resume":
            resume = True
    torch.manual_seed(0)
    train, val = load()
    model = TinyGPT(ctx=CTX)
    if resume and os.path.exists(os.path.join(HERE, "rox0.pt")):
        model.load_state_dict(torch.load(os.path.join(HERE, "rox0.pt"),
                                         weights_only=True))
        print("[train] resumed from rox0.pt", flush=True)
    print(f"[train] params={model.n_params() / 1e6:.2f}M "
          f"train_toks={len(train)} val_toks={len(val)}", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=LR)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    t0 = time.time()
    for s in range(1, steps + 1):
        model.train()
        x, y = batch_of(train, BATCH, CTX)
        opt.zero_grad()
        loss = F.cross_entropy(model(x).view(-1, 256), y.view(-1))
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        if s % 50 == 0 or s == 1:
            model.eval()
            with torch.no_grad():
                vx, vy = batch_of(val, 4, CTX)
                vl = float(F.cross_entropy(
                    model(vx).view(-1, 256), vy.view(-1)))
            dt = time.time() - t0
            print(f"[train] step {s}/{steps} loss={float(loss):.3f} "
                  f"val={vl:.3f} ({dt:.0f}s)", flush=True)
        if s % 400 == 0:
            torch.save(model.state_dict(),
                       os.path.join(HERE, "rox0.pt"))
            print("--- sample ---")
            print(sample(model, "Once upon a time there was a little girl named Lily."))
            print("----------------", flush=True)
    torch.save(model.state_dict(), os.path.join(HERE, "rox0.pt"))
    print("[train] done -> rox0.pt")


if __name__ == "__main__":
    main()
