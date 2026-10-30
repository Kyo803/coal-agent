"""One-page report of what Coal did while you were away.

    python coal_autonomy_report.py
"""
from __future__ import annotations

import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(os.path.expanduser("~"), ".coal", "autonomy")
COAL_MEM = os.path.join(os.path.expanduser("~"), ".coal")


def _tail(path, n=12):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return [ln.rstrip() for ln in f.readlines()[-n:]]
    except Exception:
        return []


def _size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def main():
    print("=" * 62)
    print("Coal — autonomy report")
    print("=" * 62)

    hb = os.path.join(STATE, "heartbeat")
    if os.path.exists(hb):
        try:
            d = json.load(open(hb, encoding="utf-8"))
            age = int(time.time() - d.get("t", 0))
            print(f"heartbeat   : {age}s ago  state={d.get('state')}  "
                  f"free_ram={d.get('free_gb')} GB  daemon={d.get('daemon_pid')}")
        except Exception:
            pass
    else:
        print("heartbeat   : (none yet)")

    stop = os.path.exists(os.path.join(STATE, "STOP"))
    print(f"stop file   : {stop}")

    print("\n--- supervisor log (tail) ---")
    for ln in _tail(os.path.join(STATE, "safe-autonomy.log"), 14):
        print(" ", ln)

    gov = os.path.join(COAL_MEM, "governance")
    print("\n--- daemon log (tail) ---")
    for ln in _tail(os.path.join(gov, "daemon.log"), 14):
        print(" ", ln)

    tel = os.path.join(gov, "telemetry.jsonl")
    print(f"\n--- telemetry ({_size(tel)/1024:.0f} KB) ---")
    counts = {}
    for ln in _tail(tel, 400):
        try:
            e = json.loads(ln)
            k = e.get("kind") or e.get("event") or "?"
            counts[k] = counts.get(k, 0) + 1
        except Exception:
            pass
    for k, v in sorted(counts.items(), key=lambda x: -x[1])[:12]:
        print(f"  {k:18s} {v}")

    print("\n--- learning ---")
    try:
        import sys
        sys.path.insert(0, HERE)
        from learning import notes
        n = getattr(notes, "stats", None)
        if callable(n):
            print(" ", json.dumps(n())[:300])
        else:
            for root, _d, fs in os.walk(os.path.join(COAL_MEM, "learning")):
                print(f"  {len(fs)} files in {root}")
                break
    except Exception as e:
        print("  (learning stats unavailable:", str(e)[:80], ")")

    print("\n--- self-improvement ---")
    for p in ("scoreboard.json", "improve.json", "history.jsonl"):
        fp = os.path.join(COAL_MEM, "selfimprove", p)
        if os.path.exists(fp):
            print(f"  {p}: {_size(fp)/1024:.0f} KB")
            for ln in _tail(fp, 6):
                print("   ", ln[:150])

    print("\n--- projects built ---")
    pr = os.path.join(COAL_MEM, "projects")
    if os.path.isdir(pr):
        for name in sorted(os.listdir(pr))[-10:]:
            print("  ", name)

    print("\n" + "=" * 62)


if __name__ == "__main__":
    main()
