"""Mission queue: an ordered list of extreme projects ROX N works through
autonomously (idle/night), recording status per mission."""
from __future__ import annotations

import json
import os
import time

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "missions")
_FILE = os.path.join(_DIR, "queue.json")

DEFAULT_ORDER = ["alu8", "bshift", "counter4", "fifo8", "uart_tx", "pwm",
                 "spi4", "seg7", "meridian-16", "vision-2", "helios-16",
                 "aldra-asm", "tess-emu", "parallax-3d"]


def _load() -> dict:
    if os.path.exists(_FILE):
        try:
            return json.load(open(_FILE, encoding="utf-8"))
        except Exception:
            pass
    return {"order": [], "status": {}, "updated": None}


def _save(d: dict) -> dict:
    d["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    return d


def ensure(order=None) -> dict:
    d = _load()
    if not d.get("order"):
        d["order"] = list(order or DEFAULT_ORDER)
    for n in d["order"]:
        d["status"].setdefault(n, "pending")
    return _save(d)


def status() -> dict:
    d = ensure()
    return d


def pending() -> list:
    d = ensure()
    return [n for n in d["order"] if d["status"].get(n) == "pending"]


def next_mission():
    p = pending()
    return p[0] if p else None


def mark(name: str, state: str) -> dict:
    d = ensure()
    d["status"][name] = state
    return _save(d)


def summary() -> dict:
    d = ensure()
    done = [n for n in d["order"] if d["status"].get(n) == "done"]
    failed = [n for n in d["order"] if d["status"].get(n) == "failed"]
    pend = pending()
    return {"order": d["order"], "pending": pend, "done": done,
            "failed": failed, "n_pending": len(pend),
            "n_done": len(done), "n_failed": len(failed)}


def reset(order=None) -> dict:
    d = {"order": list(order or DEFAULT_ORDER), "status": {}}
    for n in d["order"]:
        d["status"][n] = "pending"
    return _save(d)


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(summary(), indent=1))