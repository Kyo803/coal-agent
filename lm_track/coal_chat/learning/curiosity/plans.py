"""Learning plans across three horizons (short / mid / long).

The brain proposes its own roadmap from the curiosity graph: the frontier
becomes the near-term plan, the frontier's parents/neighbours the mid
term, and high-level high-interest areas the long term.
"""
from __future__ import annotations

from .. import paths
from .drive import rank

_FILE = "plan.json"
_DEFAULT = {"short": [], "mid": [], "long": [], "updated": None}


def load() -> dict:
    p = dict(_DEFAULT)
    p.update(paths.load_json(_FILE, {}) or {})
    return p


def save(plan: dict) -> dict:
    plan["updated"] = paths.now()
    paths.save_json(_FILE, plan)
    return plan


def propose(graph, mood) -> dict:
    top = rank(graph, mood, n=max(3, mood.effort()))
    short = [n for n, _ in top]

    mid = []
    for name in short:
        for parent in (graph.get(name) or {}).get("parents", []):
            if parent not in short and parent not in mid:
                mid.append(parent)
        for child, _w in graph.neighbors(name):
            if child not in short and child not in mid:
                mid.append(child)

    long = [n for n, t in sorted(
        graph.topics.items(),
        key=lambda kv: -float(kv[1].get("interest", 0.5)))][:8]

    return save({"short": short[:8], "mid": mid[:12], "long": long})


def current() -> dict:
    return load()
