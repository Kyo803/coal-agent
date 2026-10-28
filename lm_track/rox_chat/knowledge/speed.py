"""Speed: cache frequent retrievals and measure the speedup over time."""
from __future__ import annotations

import hashlib
import time

from . import paths

_FILE = "speed_cache.json"


def _key(query: str, k: int) -> str:
    return hashlib.sha256(f"{query}|{k}".encode()).hexdigest()[:16]


def cached_retrieve(query: str, k: int = 5, fn=None) -> dict:
    cache = paths.load_json(_FILE, {"cache": {}, "hits": 0, "misses": 0,
                                    "saved_s": 0.0})
    key = _key(query, k)
    if key in cache["cache"]:
        cache["hits"] += 1
        paths.save_json(_FILE, cache)
        return {"cached": True, "result": cache["cache"][key]}
    fn = fn or (lambda q, kk: __import__(
        "knowledge.router", fromlist=["retrieve"]).retrieve(q, kk))
    t0 = time.time()
    result = fn(query, k)
    dt = time.time() - t0
    cache["misses"] += 1
    cache["cache"][key] = result
    if len(cache["cache"]) > 500:
        for kk in list(cache["cache"])[:100]:
            cache["cache"].pop(kk, None)
    paths.save_json(_FILE, cache)
    return {"cached": False, "result": result, "elapsed": round(dt, 4)}


def stats() -> dict:
    c = paths.load_json(_FILE, {"hits": 0, "misses": 0})
    h, m = int(c.get("hits", 0)), int(c.get("misses", 0))
    total = h + m
    return {"hits": h, "misses": m,
            "hit_rate": round(h / total, 3) if total else 0.0}


def clear() -> bool:
    paths.save_json(_FILE, {"cache": {}, "hits": 0, "misses": 0,
                            "saved_s": 0.0})
    return True
