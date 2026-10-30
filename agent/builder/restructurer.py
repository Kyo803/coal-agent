"""Restructurer: when the product still isn't right, plan a rebuild.

Does not edit files itself; it produces a concrete restructure plan
(re-plan units, split/recombine, re-choose a design) that the loop feeds
back into generation.
"""
from __future__ import annotations


def propose(history: list, diagnosis: dict | None,
            criteria: list | None = None) -> dict:
    repeated = {}
    for h in history or []:
        if h.get("phase") == "COMPILE" and not h.get("ok"):
            repeated["compile"] = repeated.get("compile", 0) + 1
        if h.get("phase") == "TEST" and not h.get("ok"):
            repeated["test"] = repeated.get("test", 0) + 1

    steps = []
    if repeated.get("compile", 0) >= 2:
        steps.append("regenerate the failing unit with a stricter contract")
        steps.append("split the unit if it exceeds the size cap")
    if repeated.get("test", 0) >= 1:
        steps.append("strengthen the tests and re-derive the unit from them")
    if (diagnosis or {}).get("class") == "interface":
        steps.append("reconcile exports/imports across units (contract drift)")
    if not steps:
        steps.append("re-plan units and re-choose the design")
    return {"action": "restructure", "steps": steps,
            "reason": diagnosis or {}, "repeats": repeated}
