"""Planner: turn a topic into a concrete study plan (subtopics + questions)."""
from __future__ import annotations

from . import llm
from .curiosity.questions import generate_questions

_SYS = (
    "You decompose a learning topic into 4-6 concrete subtopics that, "
    "taken together, give solid understanding. Output ONLY JSON: "
    '{"subtopics": ["...", ...]}. No prose.'
)


def plan(topic: str, context: str = "", n: int = 5) -> dict:
    subs = []
    if llm.available():
        data = llm.json_chat([
            {"role": "system", "content": _SYS},
            {"role": "user", "content": f"TOPIC: {topic}\n\n"
                                        f"{context[:1500]}"}], timeout=120)
        if isinstance(data, dict):
            subs = data.get("subtopics") or []
        elif isinstance(data, list):
            subs = data
    subs = [str(s).strip() for s in subs if str(s).strip()][:n]
    questions = generate_questions(topic, context, n)
    return {"topic": topic, "subtopics": subs, "questions": questions}
