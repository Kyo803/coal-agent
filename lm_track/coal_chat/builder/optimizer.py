"""Quantum-inspired design optimizer.

Honest framing: these are **classical** algorithms in the quantum
*metaphor* — a state vector of design amplitudes, an energy function over
the chosen objectives, and amplitude amplification (Grover-style) that
concentrates probability on high-quality designs. No quantum hardware.

Given candidate designs it returns the best one, the Pareto frontier, and
the per-design energies/probabilities.
"""
from __future__ import annotations

import math


def _norm_range(designs, objectives):
    rng = {}
    for m in objectives["metrics"]:
        vals = [float(d.get("metrics", {}).get(m, 0.0)) for d in designs]
        rng[m] = (min(vals), max(vals)) if vals else (0.0, 1.0)
    return rng


def _normalized(design, objectives, rng):
    vec = {}
    for m, spec in objectives["metrics"].items():
        x = float(design.get("metrics", {}).get(m, 0.0))
        lo, hi = rng[m]
        n = (x - lo) / (hi - lo) if hi > lo else 0.5
        if spec.get("direction", "max") == "min":
            n = 1.0 - n
        vec[m] = n
    return vec


def energy(design, objectives, rng) -> float:
    nv = _normalized(design, objectives, rng)
    return round(sum(float(spec.get("weight", 1.0)) * (1.0 - nv[m])
                     for m, spec in objectives["metrics"].items()), 6)


def pareto(designs, objectives, rng) -> list:
    vectors = [(d, _normalized(d, objectives, rng)) for d in designs]
    front = []
    for d, v in vectors:
        dominated = False
        for d2, v2 in vectors:
            if d2 is d:
                continue
            if all(v2[m] >= v[m] for m in v) and \
               any(v2[m] > v[m] for m in v):
                dominated = True
                break
        if not dominated:
            front.append(d)
    return front


def optimize(designs: list, objectives: dict, iters: int | None = None) -> dict:
    if not designs:
        return {"best": None, "pareto": [], "energies": [],
                "probabilities": [], "iters": 0}
    rng = _norm_range(designs, objectives)
    energies = [energy(d, objectives, rng) for d in designs]
    n = len(designs)
    iters = iters or max(1, int(math.pi / 4 * math.sqrt(n)))

    mean_e = sum(energies) / n
    amp = [1.0 / math.sqrt(n)] * n
    for _ in range(iters):
        for i in range(n):
            if energies[i] < mean_e:      # oracle: mark the "good" states
                amp[i] = -amp[i]
        m = sum(amp) / n                   # diffusion about the mean
        amp = [2 * m - a for a in amp]
    probs = [a * a for a in amp]
    s = sum(probs) or 1.0
    probs = [p / s for p in probs]

    best_idx = min(range(n), key=lambda i: energies[i])
    return {
        "best": designs[best_idx],
        "best_index": best_idx,
        "energies": [round(e, 4) for e in energies],
        "probabilities": [round(p, 4) for p in probs],
        "pareto": pareto(designs, objectives, rng),
        "iters": iters,
    }
