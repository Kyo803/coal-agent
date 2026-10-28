"""Mechanics: design and test its own indexing schemes.

Different chunk sizes retrieve differently; ROX N A/B-tests them on its
own notes and records the winner, so its knowledge structure is something
it built rather than something it was given.
"""
from __future__ import annotations

from . import paths

_FILE = "mechanics.json"
SCHEMES = [400, 800, 1200, 2000]


def _chunks(text: str, width: int) -> list:
    words = (text or "").split()
    out, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def _overlap(query: str, chunk: str) -> float:
    q = {t for t in query.lower().split() if len(t) > 2}
    c = {t for t in chunk.lower().split() if len(t) > 2}
    return len(q & c) / len(q) if q else 0.0


def evaluate(width: int, samples: list, queries: list) -> float:
    docs = []
    for s in samples:
        docs.extend(_chunks(s, width))
    if not docs or not queries:
        return 0.0
    total = 0.0
    for q in queries:
        best = max((_overlap(q, d) for d in docs), default=0.0)
        total += best
    return round(total / len(queries), 4)


def experiment(samples: list, queries: list) -> dict:
    scores = {str(w): evaluate(w, samples, queries) for w in SCHEMES}
    best = max(scores, key=lambda k: scores[k])
    s = paths.load_json(_FILE, {})
    s["schemes"] = scores
    s["best"] = int(best)
    paths.save_json(_FILE, s)
    return {"schemes": scores, "best": int(best)}


def best() -> int:
    return int(paths.load_json(_FILE, {}).get("best", 800))


def stats() -> dict:
    return paths.load_json(_FILE, {})
