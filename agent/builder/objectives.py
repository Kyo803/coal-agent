"""Objectives: what "maximum possible outcome" means for a build.

The brain chooses the objective set per project (the user's directive:
"brain chooses"). The optimizer then maximises those objectives. If the
small model is unavailable, sensible per-stack defaults are used.
"""
from __future__ import annotations

# direction: "max" means bigger is better, "min" smaller is better
CATALOG = {
    "correctness": {"direction": "max", "weight": 1.0},
    "test_coverage": {"direction": "max", "weight": 0.7},
    "performance": {"direction": "max", "weight": 0.6},
    "size": {"direction": "min", "weight": 0.3},
    "elegance": {"direction": "max", "weight": 0.4},
    "accessibility": {"direction": "max", "weight": 0.4},
    "security": {"direction": "max", "weight": 0.6},
    "maintainability": {"direction": "max", "weight": 0.5},
    "ux": {"direction": "max", "weight": 0.4},
}

STACK_DEFAULTS = {
    "web": ["correctness", "accessibility", "performance", "ux",
            "maintainability"],
    "react": ["correctness", "accessibility", "ux", "maintainability"],
    "node": ["correctness", "security", "performance", "maintainability"],
    "python": ["correctness", "test_coverage", "maintainability", "security"],
    "hdl": ["correctness", "size", "performance"],
}


def choose(description: str, stack: str | None = None,
           llm_ok: bool = False) -> dict:
    metrics = {}
    rationale = ""
    if llm_ok:
        try:
            from learning import llm
            data = llm.json_chat([
                {"role": "system",
                 "content": "Choose the 3-5 most important quality "
                            "objectives for this build from: "
                            + ", ".join(CATALOG) +
                            '. Output ONLY JSON {"metrics": {"name": '
                            'weight_0_to_1}, "rationale": "..."}.'},
                {"role": "user", "content": description[:1200]}], timeout=120)
            if isinstance(data, dict) and isinstance(data.get("metrics"),
                                                     dict):
                for k, w in data["metrics"].items():
                    if k in CATALOG:
                        metrics[k] = dict(CATALOG[k], weight=float(w))
                rationale = data.get("rationale", "")
        except Exception:
            metrics = {}
    if not metrics:
        keys = STACK_DEFAULTS.get((stack or "").lower(),
                                  list(STACK_DEFAULTS["web"]))
        metrics = {k: dict(CATALOG[k]) for k in keys}
        rationale = f"default objectives for stack={stack or 'web'}"
    return {"metrics": metrics, "rationale": rationale,
            "stack": stack or "web", "description": description[:400]}


def names(objectives: dict) -> list:
    return list((objectives.get("metrics") or {}).keys())
