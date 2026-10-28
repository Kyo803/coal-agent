"""Tension: contradictions and surprise — the itch that drives learning.

  * contradictions: new claims disagree with what is already known
  * surprise: the gap between expected and actual performance/outcome
Both feed the intrinsic reward and open new questions.
"""
from __future__ import annotations

from .. import llm


def surprise(expected_mastery: float, observed_score: float) -> float:
    """0..1 — big when we did much worse/better than expected."""
    return min(1.0, abs(float(observed_score) - float(expected_mastery)))


def contradictions(new_text: str, existing: list, limit: int = 5) -> list:
    """Return [(new_claim, conflicting_claim)] using the small model.

    existing: list of dicts with a 'text' field, or list of strings.
    """
    if not new_text or not existing or not llm.available():
        return []
    olds = []
    for e in existing[:30]:
        olds.append(e.get("text", "") if isinstance(e, dict) else str(e))
    olds = [o for o in olds if o][:30]
    if not olds:
        return []
    prompt = ("NEW CLAIM:\n" + new_text[:1200] + "\n\nKNOWN:\n" +
              "\n".join(f"- {o[:300]}" for o in olds) +
              "\n\nReturn ONLY JSON: {\"contradictions\": "
              "[{\"new\": \"...\", \"conflicts\": \"...\"}]} "
              "(empty array if none).")
    data = llm.json_chat([
        {"role": "system",
         "content": "You detect factual contradictions between a new claim "
                    "and known facts. Be strict; only real conflicts."},
        {"role": "user", "content": prompt}], timeout=120)
    if isinstance(data, dict) and isinstance(data.get("contradictions"),
                                             list):
        out = []
        for c in data["contradictions"][:limit]:
            if isinstance(c, dict):
                out.append((str(c.get("new", "")), str(c.get("conflicts", ""))))
        return out
    return []
