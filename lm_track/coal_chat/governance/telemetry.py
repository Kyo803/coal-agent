"""Telemetry: is Coal healthy and getting better? Satisfaction + metrics."""
from __future__ import annotations

import time

from . import paths

_FILE = "telemetry.jsonl"


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def record(event: str, **fields) -> dict:
    rec = {"ts": _now(), "event": event}
    rec.update(fields)
    paths.append_jsonl(_FILE, rec)
    return rec


def generation_metrics() -> dict:
    metrics = {}
    try:
        from selfimprove import scoreboard
        b = scoreboard.last()
        metrics["tests_passed"] = b.get("passed")
        metrics["tests_failed"] = b.get("failed")
    except Exception:
        pass
    try:
        from learning.curiosity.graph import CuriosityGraph
        from learning.curiosity.mood import Mood
        metrics["topics"] = CuriosityGraph().stats().get("topics")
        metrics["mood"] = Mood().excitement
    except Exception:
        pass
    try:
        from learning import notes
        metrics["notes"] = notes.count()
    except Exception:
        pass
    return metrics


def satisfaction() -> float:
    """A single 0..1-ish composite of how the brain is doing."""
    m = generation_metrics()
    parts = []
    if m.get("tests_failed") is not None:
        parts.append(1.0 if m["tests_failed"] == 0 else 0.0)
    if m.get("mood") is not None:
        parts.append(float(m["mood"]))
    if m.get("notes") is not None:
        parts.append(min(1.0, m["notes"] / 100.0))
    return round(sum(parts) / len(parts), 3) if parts else 0.0


def summary(limit: int = 200) -> dict:
    recs = paths.read_jsonl(_FILE, limit=limit)
    counts = {}
    for r in recs:
        counts[r["event"]] = counts.get(r["event"], 0) + 1
    return {"events": counts, "recent": recs[-5:],
            "metrics": generation_metrics(), "satisfaction": satisfaction()}
