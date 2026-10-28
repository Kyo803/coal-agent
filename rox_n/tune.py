"""Per-deployment budget tuner (final product).

Thresholds are learned in training (train.py); top-k and expert count are
adapted per deployment by validation sweep: among configs within `tol` of
the best validation F1, pick the cheapest in analytic mult-adds.
"""
import copy
import itertools

import numpy as np
import torch

from .config import MVP_DEFAULT


def _headless_eval(n_units, top_k, threshold, n_experts, lam, X, y,
                   seed=0, hold=8):
    """No-grad streaming eval of one budget config; returns (f1, flops)."""
    from .fou import FireOnceLayer, DenseLayer
    from .plhe import HelixEmbed
    from .eme import EchoRouter
    from .stream import _f1
    torch.manual_seed(seed)
    D = X.shape[1]
    fou = FireOnceLayer(D + 4, n_units, top_k=top_k, threshold=threshold)
    dense = DenseLayer(fou)
    plhe = HelixEmbed(hold_steps=hold)
    router = EchoRouter(D + 4, n_units, n_experts=n_experts, lam=lam)
    with torch.no_grad():
        base_gate = torch.nn.Linear(D + 4, n_experts)
        base_gate.weight.copy_(router.gate.weight)
        base_gate.bias.copy_(router.gate.bias)
        base_experts = torch.nn.ModuleList(
            torch.nn.Linear(n_units, 1) for _ in range(n_experts))
        for b, r in zip(base_experts, router.experts):
            b.weight.copy_(r.weight)
            b.bias.copy_(r.bias)
    prev_S, logits_r, logits_d, f_rox = 0.0, [], [], 0
    with torch.no_grad():
        for t in range(len(X)):
            xt = torch.from_numpy(X[t])
            e_t, _ = plhe.step(float(X[t].mean()), prev_S, threshold)
            feat = torch.cat([xt, torch.tensor(e_t, dtype=torch.float32)])
            h, S, fired = fou(feat)
            prev_S = S
            logit, _, reeval = router(feat, h, S, threshold)
            hd = dense(feat)
            w = torch.softmax(base_gate(feat), dim=0)
            den = float((w * torch.stack(
                [ex(hd).squeeze() for ex in base_experts])).sum())
            logits_r.append(logit)
            logits_d.append(den)
            k = len(fired)
            f_rox += (k * (D + 4) + (n_experts * (D + 4) if reeval else 0)
                      + (n_experts if reeval else 1) * n_units)
    f_den = len(X) * (n_units * (D + 4) + n_experts * (D + 4)
                      + n_experts * n_units)
    logits_r = np.asarray(logits_r)
    n = max(32, len(X) // 5)
    det = float(np.percentile(logits_r[:n], 95))
    f1 = _f1(np.asarray(y), (logits_r > det).astype(int))
    return f1, 1.0 - f_rox / f_den


def tune_budget(X_val, y_val, n_units=128, k_options=(8, 16, 32),
                thr_options=(4.0, 8.0, 12.0), expert_options=(2, 4),
                lam=2.0, tol=0.02, seed=0):
    """Grid sweep; returns (best_cfg_dict, rows). cheapest within tol of max F1."""
    rows = []
    for k, thr, e in itertools.product(k_options, thr_options, expert_options):
        f1, saved = _headless_eval(n_units, k, thr, e, lam, X_val, y_val, seed)
        rows.append({"top_k": k, "threshold": thr, "n_experts": e,
                     "f1": round(f1, 4), "saved": round(saved, 4)})
    best_f1 = max(r["f1"] for r in rows)
    feas = [r for r in rows if r["f1"] >= best_f1 - tol]
    feas.sort(key=lambda r: -r["saved"])
    return feas[0], rows
