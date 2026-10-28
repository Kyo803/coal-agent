"""Predictor: estimate a hypothesis's risk and payoff before acting."""
from __future__ import annotations

from . import policy


def predict(hyp: dict) -> dict:
    risk = policy.risk_of(hyp)
    scope = ("config" if risk <= 1 else "tool" if risk == 2 else "core")
    confidence = 0.8 if risk <= 1 else 0.5 if risk == 2 else 0.3
    return {"risk": risk, "scope": scope, "confidence": confidence,
            "expected_gain": float(hyp.get("expected_gain", 0.1)),
            "worth_it": float(hyp.get("expected_gain", 0.1)) >= 0.2}
