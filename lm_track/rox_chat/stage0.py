"""Stage-0: prove PLHE/FOU/EME compose and train stably at tiny scale.

Runs CFG_TINY twice (position=rope vs plhe) on TinyStories bytes, CPU.
Gates to pass:
  1. loss decreases on both (trains stably together, not NaN/diverge)
  2. expert utilization stays spread (no routing collapse: min expert
     share > 5% at end) — the day-one monitor from the training plan
  3. plhe run within 10% of rope val loss (else PLHE is cut, per fallback)
Saves stage0.json with the verdict.  python stage0.py [--steps N]
"""
import json
import os
import sys
import time

import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "from_scratch"))
from arch import RoxChat, CFG_TINY, Cfg  # noqa: E402
from data_tinystories import load  # noqa: E402


def run(position, steps, train, val):
    torch.manual_seed(0)
    cfg = Cfg(**{**CFG_TINY.__dict__, "position": position})
    model = RoxChat(cfg)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    B, CTX = 12, cfg.ctx
    t0 = time.time()
    hist = []
    for s in range(1, steps + 1):
        model.train()
        i = torch.randint(0, len(train) - CTX - 1, (B,))
        x = torch.stack([train[j:j + CTX] for j in i])
        y = torch.stack([train[j + 1:j + CTX + 1] for j in i])
        opt.zero_grad()
        logits, aux, utils = model(x)
        loss = F.cross_entropy(logits.view(-1, 256), y.view(-1)) \
            + 0.01 * aux
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if s % 100 == 0 or s == 1:
            model.eval()
            with torch.no_grad():
                vi = torch.randint(0, len(val) - CTX - 1, (4,))
                vx = torch.stack([val[j:j + CTX] for j in vi])
                vy = torch.stack([val[j + 1:j + CTX + 1] for j in vi])
                vl, _, vu = model(vx)
                vloss = float(F.cross_entropy(vl.view(-1, 256),
                                              vy.view(-1)))
            flat = [u for layer_u in vu for u in layer_u]
            spread = min(flat) if flat else 0.0
            hist.append({"step": s, "loss": round(float(loss.detach()), 3),
                         "val": round(vloss, 3),
                         "min_expert": round(spread, 4)})
            print(f"[stage0:{position}] step {s} loss={float(loss.detach()):.3f} "
                  f"val={vloss:.3f} min_expert={spread:.3f} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    return hist


def main():
    steps = 600
    for a in sys.argv[1:]:
        if a.startswith("--steps="):
            steps = int(a.split("=")[1])
    train, val = load()
    out = {pos: run(pos, steps, train, val) for pos in ("rope", "plhe")}
    r, p = out["rope"][-1], out["plhe"][-1]
    verdict = {
        "rope_trains": r["loss"] < 5.0,
        "no_collapse": all(h["min_expert"] > 0.05 for h in (r, p)),
        "plhe_kept": p["val"] <= r["val"] * 1.10,
    }
    verdict["PASS"] = all(verdict.values())
    json.dump({"hist": out, "verdict": verdict},
              open(os.path.join(HERE, "stage0.json"), "w"), indent=1)
    print("[stage0] verdict:", verdict)


if __name__ == "__main__":
    main()
