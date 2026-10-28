"""Bridge to active-recall rehearsal (learning.rehearse)."""
from __future__ import annotations


def rehearse(topic: str, questions=None, k: int = 4) -> dict:
    if questions is None:
        from learning.curiosity.questions import generate_questions
        questions = generate_questions(topic)
    from learning.rehearse import rehearse as _r
    return _r(topic, questions, context_k=k)
