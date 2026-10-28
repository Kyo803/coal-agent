"""Rehearsal: active recall + spaced repetition.

ROX N generates questions about a topic, tries to answer them from what it
has learned (RAG context), and scores itself. Low scores raise the
topic's need (and its questions stay on the board).
"""
from __future__ import annotations

from .ingest import rag


def _score(answer: str, question: str) -> float:
    if not answer:
        return 0.0
    low = answer.lower()
    if "unknown" in low or "insufficient" in low or len(low.split()) < 3:
        return 0.1
    # crude: substantive, non-echoing answers score higher
    words = len(low.split())
    overlap = len(set(question.lower().split()) & set(low.split()))
    echo = overlap / max(1, len(set(question.lower().split())))
    return round(min(1.0, 0.35 + 0.05 * min(words, 60) - 0.3 * echo), 3)


def rehearse(topic: str, questions: list, context_k: int = 4) -> dict:
    from .curiosity.questions import answer
    try:
        context = rag().context(topic, k=context_k) or ""
    except Exception:
        context = ""
    items, scores = [], []
    for q in questions:
        a = answer(q, context)
        s = _score(a, q)
        scores.append(s)
        items.append({"q": q, "a": a[:600], "score": s})
    avg = round(sum(scores) / len(scores), 4) if scores else 0.0
    return {"topic": topic, "avg": avg, "items": items}
