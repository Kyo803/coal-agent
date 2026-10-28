"""ROX N observability: structured logs, latency, memory + tool traces.

Writes JSONL to <install>/logs/rox.jsonl and keeps an in-process ring of
recent turns for a live status line.

  from observability import obs
  with obs.timer("model"):
      reply = ...
  obs.turn(user, reply, kind="chat", tools=[], ms=1234)
  obs.stats()
"""
import json
import os
import time
from collections import deque
from contextlib import contextmanager

from rox_config import cfg


class Observability:
    def __init__(self, log_dir=None, level=None, capacity=200):
        self.log_dir = log_dir or cfg.observability.log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.path = os.path.join(self.log_dir, "rox.jsonl")
        self.level = level or cfg.observability.get("log_level", "info")
        self.recent = deque(maxlen=capacity)
        self.counters = {}
        self.latencies = {}
        self._t0 = time.time()

    def _emit(self, event, fields):
        rec = {"t": round(time.time(), 3), "event": event}
        rec.update(fields)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
        if self.level == "debug":
            print(f"[rox] {event} {fields}")

    @contextmanager
    def timer(self, name):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            ms = (time.perf_counter() - t0) * 1000
            self.latencies.setdefault(name, []).append(ms)
            self.latencies[name] = self.latencies[name][-500:]
            self._emit("timer", {"name": name, "ms": round(ms, 1)})

    def turn(self, user, reply, kind="chat", tools=None, ms=None,
             model=None, status=None):
        self.counters["turns"] = self.counters.get("turns", 0) + 1
        for t in (tools or []):
            name = t[0] if isinstance(t, (list, tuple)) else t
            self.counters[f"tool:{name}"] = \
                self.counters.get(f"tool:{name}", 0) + 1
        rec = {"user": (user or "")[:200], "reply": (reply or "")[:200],
               "kind": kind, "tools": [t[0] if isinstance(t, (list, tuple))
                                       else t for t in (tools or [])],
               "ms": round(ms, 1) if ms else None,
               "model": model, "status": status}
        self.recent.append(rec)
        self._emit("turn", rec)

    def stats(self):
        lat = {k: round(sum(v) / len(v), 1)
               for k, v in self.latencies.items() if v}
        return {"uptime_s": round(time.time() - self._t0, 1),
                "counters": self.counters,
                "avg_ms": lat,
                "log": self.path,
                "recent": len(self.recent)}

    def tail(self, n=5):
        return list(self.recent)[-n:]


obs = Observability()


if __name__ == "__main__":
    with obs.timer("demo"):
        time.sleep(0.05)
    obs.turn("hi", "hello", kind="simple", tools=[("search_memory", {},
                                                   "ok")], ms=42)
    print(json.dumps(obs.stats(), indent=1))
