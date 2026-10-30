"""Proposer: turn a hypothesis into a concrete, safe change.

Low-risk changes are generated deterministically (e.g. keep the curiosity
frontier seeded from unresolved questions). Code changes are only *staged*
here — they require a target, an experiment, and (for core files) an
explicit opt-in before they can be applied.
"""
from __future__ import annotations


def propose(hyp: dict, llm_ok: bool = False) -> dict | None:
    change = hyp.get("change")

    if change == "add_seed_topics":
        try:
            from learning.curiosity.graph import CuriosityGraph
            g = CuriosityGraph()
            subs = []
            for name, _ in g.frontier(30):
                for child, _w in g.neighbors(name):
                    if child not in subs and not g.get(child):
                        subs.append(child)
            topics = (subs or [n for n, _ in g.frontier(10)])[:3]
        except Exception:
            topics = []
        if not topics:
            return None
        return {"kind": "seed", "target": "config:seed_topics",
                "topics": topics,
                "rationale": "keep the curiosity frontier populated"}

    if change in ("fix_runtime_error", "fix_failing_tests"):
        if not llm_ok or not hyp.get("target"):
            return None
        return {"kind": "code", "target": hyp["target"], "content": None,
                "needs_review": True,
                "rationale": "code fix staged for review + experiment"}

    if change == "adjust_persona":
        return {"kind": "prompt", "target": "persona", "content": None,
                "needs_review": True,
                "rationale": "persona adjustment staged for review"}

    return None
