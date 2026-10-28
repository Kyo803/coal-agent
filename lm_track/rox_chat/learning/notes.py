"""Notes: durable, source-tagged records of what was learned."""
from __future__ import annotations

from . import paths

_FILE = "notes.jsonl"


def add(topic: str, text: str, source: str | None = None,
        url: str | None = None, trust: float = 0.5,
        kind: str = "note", **extra) -> dict:
    rec = {"ts": paths.now(), "topic": topic, "text": (text or "")[:8000],
           "source": source, "url": url, "trust": round(float(trust), 3),
           "kind": kind}
    rec.update(extra)
    paths.append_jsonl(_FILE, rec)
    return rec


def all_notes(limit: int | None = None) -> list:
    return paths.read_jsonl(_FILE, limit)


def recent(topic: str | None = None, limit: int = 50) -> list:
    recs = paths.read_jsonl(_FILE)
    if topic:
        recs = [r for r in recs if r.get("topic") == topic]
    return recs[-limit:]


def count(topic: str | None = None) -> int:
    recs = paths.read_jsonl(_FILE)
    if topic:
        return sum(1 for r in recs if r.get("topic") == topic)
    return len(recs)
