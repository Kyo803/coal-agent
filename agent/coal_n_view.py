"""Coal brain view — a live console of what the autonomous brain is doing.

Display-only (it does not build; the daemon does). Open it in a separate
terminal to watch Coal work its mission queue and 'think'.

    python coal_n_view.py
"""
from __future__ import annotations

import os
import time

DAEMON_LOG = os.path.join(os.path.expanduser("~"), ".coal", "governance",
                          "daemon.log")
SERVER_LOG = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Programs", "Coal", "logs",
    "llama_server.log")


def _tail(path, n=7):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return "".join(lines[-n:]).rstrip()
    except Exception:
        return "(no log yet)"


def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def main():
    from builder import mission_queue as Q

    while True:
        _clear()
        try:
            s = Q.summary()
        except Exception as e:
            s = {"n_done": 0, "n_failed": 0, "n_pending": 0, "order": [],
                 "pending": [], "error": str(e)}
        print("=" * 66)
        print("  Coal  ::  SILICON LAB  ::  autonomous brain")
        print("=" * 66)
        print(f"  queue   done {s['n_done']:2d} | failed {s['n_failed']:2d} "
              f"| pending {s['n_pending']:2d}")
        print(f"  next    {Q.next_mission()}")
        print("-" * 66)
        print("  -- Coal daemon (tasks it ran) --")
        print("  " + _tail(DAEMON_LOG).replace("\n", "\n  "))
        print("-" * 66)
        print("  -- 35B thinking (llama-server generation) --")
        print("  " + _tail(SERVER_LOG, 6).replace("\n", "\n  "))
        print("=" * 66)
        print("  (Ctrl-C to close this view; the brain keeps running)")
        time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass