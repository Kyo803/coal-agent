"""Edge-case harness (final product): flatline, noise storm, long event,
domain shift. Structural asserts (finite, bounded, ceiling) + reported
metrics. Run: python -m rox_n.robustness
"""
import numpy as np
import torch

from .config import MVP_DEFAULT
from .stream import Streamer
from .heads import load_domain


def _drive(st: Streamer, X, steps=None):
    for t in range(steps or len(X)):
        st.step_from_window(X[t % len(X)])
    return st


def scenario_flatline():
    st = Streamer(MVP_DEFAULT)
    D = st.D
    X = np.zeros((400, D), dtype=np.float32)
    for t in range(400):
        r = st.step_from_window(X[t])
        assert np.isfinite(r["S"]), "non-finite surprise on flatline"
    s = st.summary()
    return {"fires_per_step": round(st.fou.fired_unit_steps / 400 / D, 4),
            "output_frozen": bool((np.asarray(st.buf_rox)[-50:] ==
                                   st.buf_rox[-1]).all()),
            "f1": s.get("f1_rox", 0.0)}


def scenario_noise_storm():
    rng = np.random.default_rng(7)
    st = Streamer(MVP_DEFAULT)
    st.fou.fallback_patience = 8
    X = rng.standard_normal((300, st.D)).astype(np.float32) * 3.0
    maxk = 0
    for t in range(300):
        r = st.step_from_window(X[t])
        maxk = max(maxk, r["k"])
        assert np.isfinite(r["rox"]), "non-finite logit in noise storm"
    n = st.fou.n_units
    assert st.fou.unflagged_over == 0, "budget exceeded outside fallback!"
    return {"max_fired": maxk, "ceiling": st.fou.top_k, "units": n,
            "fallback_rate": round(st.fou.fallback_rate(300), 4),
            "unflagged_over_budget": st.fou.unflagged_over,
            "note": "over-ceiling steps exist only as flagged dense fallbacks"}


def scenario_long_event():
    # Sustained realistic anomaly: a real anomalous block (varying noise,
    # never identical twice) tiled 3x, so caches can't settle and the
    # budget stays saturated -> fallback must engage.
    from .heads import load_domain
    Xd, yd, _ = load_domain("ecg", seed=0)
    ones = np.where(yd == 1)[0]
    # longest anomalous run
    best, cur = (0, 0), []
    for i in ones:
        if cur and i != cur[-1] + 1:
            if len(cur) > len(best):
                best = cur
            cur = []
        cur.append(i)
    block = Xd[np.asarray(best)] if len(best) else Xd[ones[:40]]
    rng = np.random.default_rng(3)
    tiled = np.concatenate([block + 0.5 * rng.standard_normal(block.shape)
                            .astype(np.float32) for _ in range(3)])
    X = np.concatenate([Xd[:50], tiled, Xd[:50]])
    st = Streamer(MVP_DEFAULT)
    st.fou.fallback_patience = 8
    for t in range(len(X)):
        st.step_from_window(X[t])
    assert st.fou.unflagged_over == 0
    return {"event_windows": len(tiled),
            "fallback_rate": round(st.fou.fallback_rate(len(X)), 4),
            "fallback_fired": st.fou.fallback_events > 0,
            "active": round(st.fou.active_fraction(), 4)}


def scenario_domain_shift():
    # IMU windows through a head fitted on vibration stats (literally the
    # wrong fitted head): quantifies degradation without the right head.
    from .heads import HEADS, synth_imu, synth_vibration
    raw_v, _, _ = synth_vibration()
    HEADS["ecg"].fit(raw_v)
    raw, mask, _ = synth_imu()
    X, y, _ = HEADS["ecg"].transform(raw, mask)
    st = Streamer(MVP_DEFAULT)
    assert X.shape[1] == st.D, f"head dim {X.shape[1]} != core {st.D}"
    for t in range(len(X)):
        st.step_from_window(X[t])
    s = st.summary()
    return {"f1_wrong_head": round(s.get("f1_rox", 0.0), 3),
            "note": "quantifies degradation without the right input head"}


def main():
    out = {
        "flatline": scenario_flatline(),
        "noise_storm": scenario_noise_storm(),
        "long_event": scenario_long_event(),
        "domain_shift": scenario_domain_shift(),
    }
    import json
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    main()
