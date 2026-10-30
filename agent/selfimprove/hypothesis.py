"""Hypotheses: turn weakness signals into candidate self-improvements."""
from __future__ import annotations


def from_signals(signals: list) -> list:
    hyps = []
    for s in signals:
        k = s.get("kind")
        w = float(s.get("weight", 1.0))
        if k == "learning_stalled":
            hyps.append({"kind": "seed", "target": "config:seed_topics",
                         "change": "add_seed_topics",
                         "expected_gain": 0.4 * w, "reason": s.get("detail")})
        elif k == "tests_failing":
            hyps.append({"kind": "code", "target": "",
                         "change": "fix_failing_tests",
                         "expected_gain": 0.6 * w, "reason": s.get("detail")})
        elif k == "runtime_error":
            hyps.append({"kind": "code", "target": s.get("file", ""),
                         "change": "fix_runtime_error",
                         "expected_gain": 0.35 * w,
                         "reason": s.get("detail")})
        elif k == "user_correction":
            hyps.append({"kind": "prompt", "target": "persona",
                         "change": "adjust_persona",
                         "expected_gain": 0.3 * w, "reason": s.get("detail")})
    return rank(hyps)


def rank(hyps: list) -> list:
    return sorted(hyps, key=lambda h: -float(h.get("expected_gain", 0)))
