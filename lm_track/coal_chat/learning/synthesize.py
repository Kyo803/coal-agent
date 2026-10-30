"""Synthesize: distil many notes into Coal's own understanding of a topic.

The summary is written back as a note (kind="synthesis") and ingested, so
the distilled view is what future recollection and answers draw on — this
is how it develops its own ways of knowing, not just raw excerpts.
"""
from __future__ import annotations

from . import llm, notes

_SYS = (
    "You are Coal consolidating your own knowledge. Read the notes and "
    "write a compact, structured understanding of the topic: key ideas, "
    "mechanisms, trade-offs, and open questions. Be precise and non-"
    "redundant. Plain text, <= 220 words."
)


def synthesize(topic: str, limit: int = 12) -> str:
    recs = notes.recent(topic, limit=limit)
    recs = [r for r in recs if r.get("kind") != "synthesis"]
    if not recs:
        return ""
    joined = "\n\n".join(
        f"[{r.get('source') or r.get('url') or 'note'}] {r['text'][:1000]}"
        for r in recs)
    summary = ""
    if llm.available():
        summary = llm.chat([
            {"role": "system", "content": _SYS},
            {"role": "user", "content": f"TOPIC: {topic}\n\n{joined[:5000]}"}],
            timeout=150)
    if not summary:
        summary = joined[:1500]
    notes.add(topic, summary, source="synthesis", kind="synthesis",
              trust=0.6)
    try:
        from .ingest import rag
        rag().ingest_text(summary, source=f"synthesis:{topic}")
    except Exception:
        pass
    return summary
