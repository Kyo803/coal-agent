"""Curriculum: order learning so prerequisites come first.

Given a set of target topics, walk each topic's parents (prerequisites)
before the topic itself; then interleave by interest so the path is both
sound and engaging.
"""
from __future__ import annotations


def order(graph, topics: list) -> list:
    ordered, seen = [], set()

    def visit(t):
        if t in seen or not graph.get(t):
            return
        seen.add(t)
        for parent in (graph.get(t) or {}).get("parents", []):
            visit(parent)
        ordered.append(t)

    for t in topics:
        visit(t)
    return ordered


def sequence(graph, n: int = 10) -> list:
    from .curiosity.drive import rank
    from .curiosity.mood import Mood
    picks = [name for name, _ in rank(graph, Mood(), n=n)]
    return order(graph, picks)
