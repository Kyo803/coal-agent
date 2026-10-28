"""Bridge to prerequisite-ordered curriculum (learning.curriculum)."""
from __future__ import annotations


def order(graph, topics: list) -> list:
    from learning.curriculum import order as _o
    return _o(graph, topics)


def sequence(graph=None, n: int = 10) -> list:
    if graph is None:
        from learning.curiosity.graph import CuriosityGraph
        graph = CuriosityGraph()
    from learning.curriculum import sequence as _s
    return _s(graph, n=n)
