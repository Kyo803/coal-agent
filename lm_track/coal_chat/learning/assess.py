"""Self-assessment: how well does Coal actually know a topic?

Combines retrieval coverage (can it find relevant material?) with the
volume of notes and (optionally) rehearsal scores, to estimate mastery and
surface gaps (subtopics still unanswered).
"""
from __future__ import annotations

from . import notes
from .ingest import rag


def coverage(topic: str, k: int = 6) -> float:
    try:
        hits = rag().search(topic, k=k)
    except Exception:
        return 0.0
    if not hits:
        return 0.0
    sims = [float(h.get("score", 0)) for h in hits]
    return round(min(1.0, sum(sims) / max(1, len(sims))), 4)


def mastery(topic: str, rehearsal: float | None = None) -> float:
    cov = coverage(topic)
    n = notes.count(topic)
    base = 0.55 * cov + 0.45 * min(1.0, n / 10.0)
    if rehearsal is not None:
        base = 0.45 * cov + 0.25 * min(1.0, n / 10.0) + 0.30 * rehearsal
    return round(min(1.0, base), 4)


def gaps(topic: str, limit: int = 5) -> list:
    """Return open questions recorded for a topic (things not yet nailed)."""
    from .curiosity.graph import CuriosityGraph
    t = CuriosityGraph().get(topic) or {}
    return list(t.get("questions", []))[:limit]


def report(topic: str) -> dict:
    return {"topic": topic, "coverage": coverage(topic),
            "notes": notes.count(topic), "mastery": mastery(topic),
            "gaps": gaps(topic)}
