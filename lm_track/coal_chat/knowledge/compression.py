"""Compression: distil knowledge into concepts (and measure the ratio)."""
from __future__ import annotations

from . import paths

_FILE = "compression.json"


def compress(topic: str, min_notes: int = 3) -> dict:
    from learning import notes
    from learning.synthesize import synthesize
    n = notes.count(topic)
    if n < min_notes:
        return {"ok": False, "reason": f"only {n} notes (< {min_notes})"}
    recs = notes.recent(topic, limit=50)
    before = sum(len(r.get("text") or "") for r in recs)
    summary = synthesize(topic) or ""
    after = len(summary)
    ratio = round(after / before, 4) if before else 1.0
    data = paths.load_json(_FILE, {"topics": {}})
    data["topics"][topic] = {"notes": n, "before": before,
                             "after": after, "ratio": ratio}
    paths.save_json(_FILE, data)
    return {"ok": True, "topic": topic, "before": before, "after": after,
            "ratio": ratio}


def stats() -> dict:
    return paths.load_json(_FILE, {"topics": {}})
