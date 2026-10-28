"""Fallback Enforcer: resilience section-7 hierarchy as executable code.

Priority table (highest first):
 1. retrieval down + high confidence -> answer but flag UNVERIFIED
 2. retrieval down + low confidence  -> refuse to guess, state limit
 3. tool failure mid-reasoning       -> labeled estimate, never silent swap
 4. memory conflicts with user       -> defer to user's restated version
 5. outside alignment coverage       -> state uncertainty, no confabulation
Every row has a unit test below. evals.py calls run_all() as a CI gate.
"""
from attachments import tool_gate, lockout_check
from retrieval import BM25


def enforce(situation):
    """situation dict -> (text, action_code). Deterministic policy."""
    k = situation["kind"]
    if k == "retrieval_down_confident":
        return (situation["draft"] + " [UNVERIFIED — index unavailable]",
                "flag_unverified")
    if k == "retrieval_down_unsure":
        return ("I can't verify this right now and I'm not confident — "
                "I won't guess.", "refuse")
    if k == "tool_failed":
        return (situation.get("estimate", "no estimate")
                + " [estimate — computation could not be verified]",
                "labeled_estimate")
    if k == "memory_conflict":
        return ("Going with your restated version: "
                + situation["user_version"], "defer_to_user")
    if k == "ood_request":
        return ("I'm not sure how to handle that request reliably.",
                "state_uncertainty")
    raise ValueError(k)


def selftest():
    t, a = enforce({"kind": "retrieval_down_confident", "draft": "Paris"})
    assert a == "flag_unverified" and "UNVERIFIED" in t
    t, a = enforce({"kind": "retrieval_down_unsure"})
    assert a == "refuse" and "won't guess" in t
    t, a = enforce({"kind": "tool_failed", "estimate": "about 42"})
    assert a == "labeled_estimate" and "estimate" in t
    t, a = enforce({"kind": "memory_conflict", "user_version": "Biscuit"})
    assert a == "defer_to_user" and "Biscuit" in t
    t, a = enforce({"kind": "ood_request"})
    assert a == "state_uncertainty"
    # live-fire: real outage through str_answer + real tool error
    from retrieval import str_answer
    idx = BM25(["Paris is the capital of France."])
    idx.down = True
    r = str_answer("capital of France?",
                   lambda q: ("Paris", 0.1, "paris", ["paris", "lyon"]), idx)
    assert r["status"] == "index-down", r
    _, tt = tool_gate("compute 1/0 now")
    assert "could not be verified" in tt
    print("[fallbacks] selftest OK (5 policy rows + 2 live drills)")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if selftest() else 1)
