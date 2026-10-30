"""Observer: find where Coal is weak (the input to self-improvement).

Signals come from: explicit notes, the learning journal (stalled cycles),
runtime logs (tracebacks), and the last scoreboard (failing tests).
"""
from __future__ import annotations

import os
import re

from coal_config import cfg

from . import paths

TRACE = re.compile(r"Traceback \(most recent call last\)|^[A-Za-z_.]+Error:",
                   re.M)


def add_signal(kind: str, detail: str, weight: float = 1.0,
               **extra) -> dict:
    rec = {"ts": paths.now() if hasattr(paths, "now") else _now(),
           "kind": kind, "detail": detail, "weight": weight}
    rec.update(extra)
    paths.append_jsonl("signals.jsonl", rec)
    return rec


def _now():
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _learning_stalled(n: int = 5) -> list:
    try:
        from learning import paths as lp
    except Exception:
        return []
    recs = lp.read_jsonl("journal.jsonl", limit=n)
    if len(recs) < n:
        return []
    stalled = sum(1 for r in recs if not r.get("sources"))
    if stalled >= n:
        return [{"kind": "learning_stalled", "weight": 0.6,
                 "detail": f"last {n} cycles found no sources"}]
    return []


def _runtime_errors(max_files: int = 8) -> list:
    out = []
    d = cfg.observability.get("log_dir")
    if not d or not os.path.isdir(d):
        return out
    try:
        logs = [f for f in os.listdir(d) if f.endswith(".log")]
    except Exception:
        return out
    for fn in logs[:max_files]:
        p = os.path.join(d, fn)
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()[-20000:]
        except Exception:
            continue
        if TRACE.search(txt):
            out.append({"kind": "runtime_error", "weight": 0.8,
                        "detail": f"traceback detected in {fn}",
                        "file": fn})
    return out


def _tests_failing() -> list:
    try:
        from . import scoreboard
        b = scoreboard.last()
    except Exception:
        return []
    if b.get("failed", 0) > 0:
        return [{"kind": "tests_failing", "weight": 1.0,
                 "detail": f"{b['failed']} failing checks in last board"}]
    return []


def collect() -> list:
    out = []
    out += _learning_stalled()
    out += _runtime_errors()
    out += _tests_failing()
    for s in paths.read_jsonl("signals.jsonl", limit=50):
        out.append(s)
    # dedupe by kind
    seen, uniq = set(), []
    for s in out:
        k = s.get("kind")
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)
    return uniq
