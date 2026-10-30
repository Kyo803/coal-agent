"""Estimate the fine-tune (cost/time) and describe the plan."""
from __future__ import annotations

from . import cookbook, dataset


def estimate(n_examples: int, epochs: int = 2) -> dict:
    # rough: ~600 tokens/example, ~1.5 s/step on a 40GB card with bs1+ga8
    tokens = n_examples * 600
    steps = max(1, int(n_examples / 8) * epochs)
    gpu_hours = round(steps * 1.5 / 3600, 2)
    return {"examples": n_examples, "epochs": epochs, "tokens": tokens,
            "steps": steps, "gpu_hours": gpu_hours,
            "cost_usd": [round(gpu_hours * 1.0, 2),
                         round(gpu_hours * 2.5, 2)]}


def plan() -> dict:
    try:
        from learning import notes
        n = max(0, notes.count())
    except Exception:
        n = 0
    est = estimate(max(50, n * 2))
    return {"base_model": cookbook.base_model(),
            "dataset_dir": dataset.dir(),
            "estimate": est,
            "runbook": cookbook.runbook()}
