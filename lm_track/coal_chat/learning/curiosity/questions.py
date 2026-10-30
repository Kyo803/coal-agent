"""Question generation — Coal forms its own questions about a topic.

Uses the small model; falls back to template questions if it is offline,
so the drive never stalls.
"""
from __future__ import annotations

from .. import llm

_SYSTEM = (
    "You are Coal's curiosity engine. Given a topic and any context, "
    "produce SHARP, specific, answerable questions that would deepen "
    "understanding (mechanisms, edge cases, trade-offs, how/why). Output "
    "ONLY a JSON array of strings, 4-6 items, no prose."
)

_FALLBACK = [
    "What exactly is {t}?",
    "Why does {t} matter — what does it enable?",
    "How does {t} work under the hood?",
    "What are the main trade-offs or failure modes of {t}?",
    "What is a concrete, non-trivial example of {t}?",
    "How does {t} relate to adjacent ideas?",
]


def generate_questions(topic: str, context: str = "", n: int = 5) -> list:
    if llm.available():
        user = f"TOPIC: {topic}\n\nCONTEXT:\n{context[:1500]}"
        data = llm.json_chat([{"role": "system", "content": _SYSTEM},
                              {"role": "user", "content": user}],
                             timeout=120)
        qs = None
        if isinstance(data, list):
            qs = [str(x).strip() for x in data if str(x).strip()]
        elif isinstance(data, dict):
            for k in ("questions", "items", "q"):
                if isinstance(data.get(k), list):
                    qs = [str(x).strip() for x in data[k] if str(x).strip()]
                    break
        if qs:
            return qs[:n]
    return [tpl.format(t=topic) for tpl in _FALLBACK[:n]]


def answer(question: str, context: str) -> str:
    if not llm.available():
        return ""
    return llm.chat([
        {"role": "system",
         "content": "Answer the question concisely using ONLY the context. "
                    "If the context is insufficient, say 'unknown'."},
        {"role": "user", "content": f"CONTEXT:\n{context[:2000]}\n\n"
                                    f"QUESTION: {question}"}],
        timeout=120)
