"""Policy: how much autonomy a given change gets.

Risk tiers decide whether a change is auto-applied, must win an isolated
experiment first, or is refused. Anti-oscillation rate-limits changes, and
high-risk code changes require an explicit opt-in.
"""
from __future__ import annotations

import time

from . import paths

RISK = {"config": 0, "seed": 0, "langpack": 1, "prompt": 1,
        "tool": 2, "code": 3, "core": 4}

# files that must never be auto-edited without an opt-in
CORE_FILES = {"coal.py", "server_manager.py", "coal_config.py",
              "memory/embed.py", "tools/exec.py", "tools/permissions.py"}


def risk_of(hyp: dict) -> int:
    kind = hyp.get("kind", "code")
    target = (hyp.get("target") or "").replace("\\", "/")
    if target in CORE_FILES:
        return RISK["core"]
    if target.startswith("learning/"):
        return min(RISK["code"], 3)
    return RISK.get(kind, 2)


def _last_apply_ts() -> float:
    recs = paths.read_jsonl("applied.jsonl", 1)
    if not recs:
        return 0.0
    try:
        return time.mktime(time.strptime(recs[-1]["ts"],
                                         "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return 0.0


def decide(hyp: dict, dry_run: bool = True, allow_high_risk: bool = False,
           experiment_passed: bool | None = None,
           min_interval_s: int = 300,
           now: float | None = None) -> dict:
    risk = risk_of(hyp)
    now = now if now is not None else time.time()

    if dry_run:
        return {"action": "dry_run", "risk": risk,
                "reason": "dry-run mode (nothing applied)"}

    # anti-oscillation
    last = _last_apply_ts()
    if last and (now - last) < min_interval_s:
        return {"action": "refuse", "risk": risk,
                "reason": f"rate-limited ({int(now - last)}s < "
                          f"{min_interval_s}s since last change)"}

    if risk >= 3:
        if not allow_high_risk:
            return {"action": "refuse", "risk": risk,
                    "reason": "high-risk code change (set "
                              "selfimprove.allow_high_risk to enable)"}
        if experiment_passed is not True:
            return {"action": "experiment", "risk": risk,
                    "reason": "high-risk change must win an experiment"}
        return {"action": "apply", "risk": risk,
                "reason": "high-risk change approved + experiment passed"}

    if risk == 2:
        if experiment_passed is True:
            return {"action": "apply", "risk": risk,
                    "reason": "tool change passed its experiment"}
        return {"action": "experiment", "risk": risk,
                "reason": "tool change must win an experiment"}

    # risk 0-1: config/langpack/prompt — validate then apply
    return {"action": "apply", "risk": risk,
            "reason": "low-risk change (validated)"}
