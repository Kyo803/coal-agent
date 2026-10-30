"""FIM — Fast Interaction Matrix via gradient-conflict screening.

Full matrix.py retrains every cell (4 x 300 steps). FIM instead runs ONE
short all-on run and, every K steps, measures cosine similarity between
per-mechanism loss gradients (LM vs balance-aux vs sparse-aux, PCGrad
family). Strong negative alignment = mechanisms fight = quarantine
candidate without any retraining.

Honest scope: FIM detects CONFLICT, not necessity. Absence of conflict
does not prove a mechanism load-bearing (matrix.py proved balance-aux
necessary via collapse). The two compose: quarantine if matrix-bad OR
strong-conflict. Position schemes (rope/plhe) have no loss term, so no
gradient exists to compare — they stay in the (now halved) training
matrix. The script states this split instead of pretending one number
covers everything.
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
from arch import CoalChat, CFG_TINY  # noqa: E402
from data_tinystories import load  # noqa: E402

STEPS = 60
PROBE_EVERY = 10
CONFLICT_THR = -0.2


def flat_grad(loss, params):
    gs = torch.autograd.grad(loss, params, retain_graph=True,
                             allow_unused=True)
    parts = []
    for g, p in zip(gs, params):
        v = g.reshape(-1) if g is not None \
            else torch.zeros(p.numel(), device=p.device)
        parts.append(v / (v.norm() + 1e-12))
    full = torch.cat(parts)
    return full / (full.norm() + 1e-12), parts


def cos(a, b):
    return float((a * b).sum())


def group_cos(pa, pb):
    """Min over parameter tensors: catches conflict localized in a
    small subspace (e.g. gate weights) that full-vector cosine dilutes."""
    cs = [float((a * b).sum()) for a, b in zip(pa, pb)]
    i = int(min(range(len(cs)), key=lambda j: cs[j]))
    return cs[i], i


def fim_run(steps=STEPS, batch=8):
    torch.manual_seed(0)
    train, _ = load()
    m = CoalChat(CFG_TINY)
    opt = torch.optim.AdamW(m.parameters(), lr=3e-4)
    params = [p for p in m.parameters() if p.requires_grad]
    B, CTX = batch, m.cfg.ctx
    acc = {"lm_bal": [], "lm_sp": [], "bal_sp": []}
    gmin = {"lm_bal": [], "lm_sp": [], "bal_sp": []}
    names = [n for n, _ in m.named_parameters() if _.requires_grad]
    t0 = time.time()
    for s in range(1, steps + 1):
        m.train()
        i = torch.randint(0, len(train) - CTX - 1, (B,))
        x = torch.stack([train[j:j + CTX] for j in i])
        y = torch.stack([train[j + 1:j + CTX + 1] for j in i])
        opt.zero_grad()
        logits, parts, _ = m.forward_parts(x)
        lm = F.cross_entropy(logits.view(-1, 256), y.view(-1))
        (lm + 0.01 * (parts["balance"] + parts["sparse"])).backward()
        opt.step()
        if s % PROBE_EVERY == 0:
            m.train()
            opt.zero_grad()
            logits, parts, _ = m.forward_parts(x)
            lm2 = F.cross_entropy(logits.view(-1, 256), y.view(-1))
            g_lm, p_lm = flat_grad(lm2, params)
            g_bal, p_bal = flat_grad(parts["balance"], params)
            g_sp, p_sp = flat_grad(parts["sparse"], params)
            acc["lm_bal"].append(cos(g_lm, g_bal))
            acc["lm_sp"].append(cos(g_lm, g_sp))
            acc["bal_sp"].append(cos(g_bal, g_sp))
            for key, (a, b) in (("lm_bal", (p_lm, p_bal)),
                                ("lm_sp", (p_lm, p_sp)),
                                ("bal_sp", (p_bal, p_sp))):
                c, i = group_cos(a, b)
                gmin[key].append((c, names[i]))
            opt.zero_grad()
    dt = time.time() - t0
    gmin_out = {k: {"min_cos": round(min(c for c, _ in v), 4),
                    "where": min(v)[1]} for k, v in gmin.items()}
    return ({k: round(sum(v) / len(v), 4) for k, v in acc.items()},
            gmin_out, dt)


def reference_cell_time(steps=300, batch=8):
    """Time one full-matrix cell for the speedup denominator."""
    torch.manual_seed(0)
    train, _ = load()
    m = CoalChat(CFG_TINY)
    opt = torch.optim.AdamW(m.parameters(), lr=3e-4)
    B, CTX = batch, m.cfg.ctx
    t0 = time.time()
    for _ in range(steps):
        i = torch.randint(0, len(train) - CTX - 1, (B,))
        x = torch.stack([train[j:j + CTX] for j in i])
        y = torch.stack([train[j + 1:j + CTX + 1] for j in i])
        opt.zero_grad()
        logits, aux, _ = m(x)
        (F.cross_entropy(logits.view(-1, 256), y.view(-1))
         + 0.01 * aux).backward()
        opt.step()
    return time.time() - t0


def main():
    scores, gmin, fim_t = fim_run()
    cell_t = reference_cell_time()
    full_t = 4 * cell_t  # 4-cell matrix at equal steps
    ground = json.load(open(os.path.join(HERE, "matrix.json")))
    conflict = {k: v for k, v in scores.items() if v < CONFLICT_THR}
    gloc = {k: v for k, v in gmin.items()
            if v["min_cos"] < CONFLICT_THR}
    if gloc and not list(ground["quarantine"]):
        verdict = ("FIM-only tension with healthy matrix outcome — "
                   "mechanisms interact (expected MoE tension at the "
                   "router) but the outcome is good: keep, monitor.")
    elif gloc:
        verdict = ("Tension localized at router gate weights (LM loss "
                   "vs balance aux, expected MoE tension) AND matrix "
                   "quarantines no-aux cells: aux is necessary AND "
                   "fights for it — keep aux, governor stays mandatory.")
    else:
        verdict = "No conflict detected at any granularity."
    out = {
        "conflict_scores": scores,
        "min_group": gmin,
        "conflict_thr": CONFLICT_THR,
        "conflicts": conflict,
        "group_conflicts": gloc,
        "fim_seconds": round(fim_t, 1),
        "full_matrix_seconds": round(full_t, 1),
        "speedup": round(full_t / max(fim_t, 1e-6), 1),
        "matrix_quarantine": ground["quarantine"],
        "verdict": verdict,
    }
    json.dump(out, open(os.path.join(HERE, "fim.json"), "w"), indent=1)
    print("[fim]", json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    main()
