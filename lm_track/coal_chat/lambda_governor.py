"""Lambda Governor: closed-loop EME hysteresis control.

Fixed lambda either collapses experts (stickiness wins) or churns
(balance loss wins). The governor reads expert-utilization entropy H
every step and adapts per-MoE-layer lambda:
  H healthy (near logE)  -> lambda rises toward cap (stability pays)
  H below floor          -> lambda -> 0 + force full re-eval M steps
                            (escape collapse)
  H pegged max + churn   -> lambda capped (churn guard via reeval rate)
Swap-in: EME(cfg, governor=gov, layer_id=i); gov.query(i) replaces the
fixed eme_lambda; gov.observe(i, util_vector, reevaluated) each step.
"""
import math


class Governor:
    def __init__(self, n_experts, floor_frac=0.6, cap=4.0, step=0.2,
                 escape_steps=8, churn_reeval_max=0.9, window=200):
        self.E = n_experts
        self.floor = floor_frac * math.log(n_experts)
        self.cap = cap
        self.step = step
        self.escape_steps = escape_steps
        self.churn_max = churn_reeval_max
        self.window = window
        self.lam = {}       # layer_id -> current lambda
        self.escape = {}    # layer_id -> remaining forced re-evals
        self.reeval_hist = {}  # layer_id -> recent reeval flags

    def _entropy(self, util):
        return -sum(max(u, 1e-12) * math.log(max(u, 1e-12)) for u in util)

    def observe(self, layer, util, reevaluated):
        H = self._entropy(util)
        lam = self.lam.get(layer, 2.0)
        hist = self.reeval_hist.get(layer, [])
        hist.append(1 if reevaluated else 0)
        self.reeval_hist[layer] = hist[-self.window:]
        if H < self.floor:
            lam = 0.0
            self.escape[layer] = self.escape_steps
        elif sum(hist) / max(1, len(hist)) > self.churn_max and len(hist) >= 20:
            lam = max(0.0, lam - self.step)  # churn guard
        else:
            lam = min(self.cap, lam + self.step)
        self.lam[layer] = lam
        return H, lam

    def query(self, layer):
        if self.escape.get(layer, 0) > 0:
            self.escape[layer] -= 1
            return None  # None = force re-eval, ignore incumbent
        return self.lam.get(layer, 2.0)


def selftest():
    g = Governor(8)
    # collapse: one expert takes all -> escape must fire, lambda -> 0
    H, lam = g.observe("l0", [0.93] + [0.01] * 7, True)
    assert lam == 0.0 and g.query("l0") is None, (H, lam)
    for _ in range(7):
        assert g.query("l0") is None  # escape window: 8 Nones total
    assert g.query("l0") == 0.0  # window spent, lambda still 0
    # healthy: uniform -> lambda climbs to cap
    for _ in range(25):
        H, lam = g.observe("l1", [0.125] * 8, False)
    assert lam == 4.0, lam
    # churn: always re-evaluating -> lambda pushed down
    for _ in range(60):
        H, lam = g.observe("l2", [0.125] * 8, True)
    assert lam < 4.0, lam
    import math as _m
    h_collapse = -(0.93 * _m.log(0.93) + 7 * 0.01 * _m.log(0.01))
    print(f"[governor] selftest OK (collapse H={h_collapse:.2f} "
          f"floor={g.floor:.2f})")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if selftest() else 1)
