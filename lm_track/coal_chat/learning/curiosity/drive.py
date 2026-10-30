"""Intrinsic reward ("dopamine") that decides what to learn next.

reward = novelty + curiosity(frontier proximity) + competence potential
         + interest + surprise, modulated by the current mood.

This is deliberately not goal-driven: it encourages exploration of the
unexplored and consolidation of the half-known.
"""
from __future__ import annotations


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def novelty(name, graph) -> float:
    t = graph.get(name)
    if not t:
        return 1.0
    return _clamp((1.0 - float(t.get("mastery", 0.0)))
                  / (1.0 + 0.5 * int(t.get("visits", 0))))


def proximity(name, graph) -> float:
    """How learnable a topic is now: adjacent to things already known."""
    neigh = graph.neighbors(name)
    if not neigh:
        return 0.5
    known = sum(1 for n, _w in neigh
                if float((graph.get(n) or {}).get("mastery", 0)) > 0.4)
    return _clamp(0.3 + 0.2 * known)


def reward(name, graph, mood, surprise=0.0) -> float:
    t = graph.get(name) or {}
    interest = float(t.get("interest", 0.5))
    mastery = float(t.get("mastery", 0.0))
    nov = novelty(name, graph)
    prox = proximity(name, graph)
    competence = 1.0 - mastery
    r = (0.35 * nov + 0.25 * prox + 0.20 * competence
         + 0.10 * interest + 0.10 * _clamp(surprise))
    r += 0.15 * mood.exploration_bonus() * nov
    return round(_clamp(r), 4)


def rank(graph, mood, n=5) -> list:
    scored = [(name, reward(name, graph, mood))
              for name, _ in graph.frontier(60)]
    scored.sort(key=lambda kv: -kv[1])
    return scored[:n]
