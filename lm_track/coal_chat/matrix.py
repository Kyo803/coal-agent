"""Interaction Matrix Runner: pairwise mechanism ablation at small scale.

19 mechanisms interact; pairwise testing beats hoping. Cells vary the
TRAINING-side knobs that exist: position scheme (rope/plhe) x aux-loss
weight (balance+sparse aux on/off). Governor/hysteresis are inference-
side and covered by lambda_governor.selftest + arch infer smoke, not
by this training matrix — the script documents that split instead of
pretending one harness covers both.
Output: heatmap JSON + quarantine recommendations. CPU demo: 4 cells x
300 steps on CFG_TINY bytes.
"""
import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PAIRS = [("rope", "plhe"), ("aux_on", "aux_off")]


def run_cell(position, aux_w, steps, train, val):
    import torch
    import torch.nn.functional as F
    from arch import CoalChat, CFG_TINY, Cfg
    torch.manual_seed(0)
    cfg = Cfg(**{**CFG_TINY.__dict__, "position": position})
    m = CoalChat(cfg)
    opt = torch.optim.AdamW(m.parameters(), lr=3e-4)
    B, CTX = 8, cfg.ctx
    for s in range(steps):
        m.train()
        i = torch.randint(0, len(train) - CTX - 1, (B,))
        x = torch.stack([train[j:j + CTX] for j in i])
        y = torch.stack([train[j + 1:j + CTX + 1] for j in i])
        opt.zero_grad()
        logits, aux, _ = m(x)
        (F.cross_entropy(logits.view(-1, 256), y.view(-1))
         + aux_w * aux).backward()
        opt.step()
    m.eval()
    with torch.no_grad():
        vi = torch.randint(0, len(val) - CTX - 1, (4,))
        vx = torch.stack([val[j:j + CTX] for j in vi])
        vy = torch.stack([val[j + 1:j + CTX + 1] for j in vi])
        vl, _, vu = m(vx)
        loss = float(F.cross_entropy(vl.view(-1, 256), vy.view(-1)))
    flat = [u for lu in vu for u in lu]
    return {"val": round(loss, 3),
            "min_expert": round(min(flat), 4) if flat else 0.0}


def main():
    steps = 300
    for a in sys.argv[1:]:
        if a.startswith("--steps="):
            steps = int(a.split("=", 1)[1])
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "from_scratch"))
    from data_tinystories import load
    train, val = load()
    rows = {}
    for pos, aux in [("rope", 0.01), ("rope", 0.0), ("plhe", 0.01),
                     ("plhe", 0.0)]:
        key = f"{pos}/aux={aux}"
        rows[key] = run_cell(pos, aux, steps, train, val)
        print(f"[matrix] {key}: {rows[key]}", flush=True)
    base = rows["rope/aux=0.01"]["val"]
    quarantine = [k for k, v in rows.items()
                  if v["val"] > base * 1.1 or v["min_expert"] < 0.05]
    out = {"rows": rows, "quarantine": quarantine}
    json.dump(out, open(os.path.join(HERE, "matrix.json"), "w"), indent=1)
    print("[matrix] quarantine:", quarantine)
    return out
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "from_scratch"))
    from data_tinystories import load
    train, val = load()
    rows = {}
    for pos, lam in [("rope", True), ("rope", False), ("plhe", True),
                     ("plhe", False)]:
        key = f"{pos}/gov={lam}"
        rows[key] = run_cell(pos, lam, steps, train, val)
        print(f"[matrix] {key}: {rows[key]}", flush=True)
    base = rows["rope/gov=True"]["val"]
    quarantine = [k for k, v in rows.items()
                  if v["val"] > base * 1.1 or v["min_expert"] < 0.05]
    out = {"rows": rows, "quarantine": quarantine}
    json.dump(out, open(os.path.join(HERE, "matrix.json"), "w"), indent=1)
    print("[matrix] quarantine:", quarantine)
    return out


if __name__ == "__main__":
    main()
