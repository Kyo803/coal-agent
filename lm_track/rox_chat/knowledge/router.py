"""Retrieval router: ROX N learns which way of remembering works best.

A multi-armed bandit (UCB1) over retrieval routes — semantic (RAG),
keyword (notes), recency (notes). Each route is rewarded when it returns
usable hits, so recall strategies that work get used more: the brain
builds its own routes to knowledge.
"""
from __future__ import annotations

import math

from . import paths

_FILE = "router.json"
ROUTES = ["semantic", "keyword", "recency"]


def _state():
    return paths.load_json(_FILE, {"routes": {}, "total": 0})


def _save(s):
    paths.save_json(_FILE, s)


def choose(routes=None) -> str:
    s = _state()
    routes = routes or ROUTES
    total = max(1, int(s.get("total", 0)))
    best, best_score = None, -1.0
    for r in routes:
        d = s["routes"].get(r, {"pulls": 0, "reward": 0.0})
        if d["pulls"] == 0:
            return r
        mean = d["reward"] / d["pulls"]
        score = mean + math.sqrt(2 * math.log(total) / d["pulls"])
        if score > best_score:
            best_score, best = score, r
    return best or routes[0]


def update(route: str, reward: float) -> None:
    s = _state()
    d = s["routes"].setdefault(route, {"pulls": 0, "reward": 0.0})
    d["pulls"] += 1
    d["reward"] += float(reward)
    s["total"] = int(s.get("total", 0)) + 1
    _save(s)


def _run(route: str, query: str, k: int) -> list:
    if route == "semantic":
        from learning.ingest import rag
        return rag().search(query, k=k)
    if route == "keyword":
        from learning import notes
        toks = [t for t in query.lower().split() if len(t) > 2]
        out = []
        for r in notes.all_notes():
            txt = (r.get("text") or "").lower()
            score = sum(txt.count(t) for t in toks)
            if score:
                out.append({"text": r["text"], "source": r.get("source"),
                            "score": score})
        out.sort(key=lambda x: -x["score"])
        return out[:k]
    if route == "recency":
        from learning import notes
        return [{"text": r["text"], "source": r.get("source"),
                 "score": 1.0} for r in notes.recent(query, limit=k)]
    return []


def retrieve(query: str, k: int = 5, route: str | None = None) -> dict:
    route = route or choose()
    hits = _run(route, query, k)
    update(route, 1.0 if hits else 0.0)
    return {"route": route, "hits": hits, "n": len(hits)}


def stats() -> dict:
    return _state()
