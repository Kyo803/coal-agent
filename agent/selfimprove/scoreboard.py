"""Generation scoreboard: is the self actually getting better?

Measures each generation by running the test suites and recording counts,
tool-registry size, and learning-brain size. Used to compare a candidate
change against the current self and to trigger rollback on regression.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

from . import paths

SUITES = ["test_tools", "test_security", "test_chip", "test_board",
          "test_learning"]
LINE = re.compile(r"(\d+)\s+passed,\s+(\d+)\s+failed")


def _run(name, root, timeout):
    script = os.path.join(root, name + ".py")
    if not os.path.exists(script):
        return None
    try:
        p = subprocess.run([sys.executable, "-u", script], cwd=root,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout,
                           creationflags=paths.CREATE_NO_WINDOW)
        m = LINE.search((p.stdout or "") + (p.stderr or ""))
        if m:
            return {"passed": int(m.group(1)), "failed": int(m.group(2))}
        # no actionable summary: treat a non-zero exit as a crash
        crashed = 1 if p.returncode != 0 else 0
        return {"passed": 0, "failed": crashed, "rc": p.returncode}
    except subprocess.TimeoutExpired:
        return {"passed": 0, "failed": 1, "error": "timeout"}
    except Exception as e:
        return {"passed": 0, "failed": -1, "error": str(e)}


def registry_size(root):
    try:
        sys.path.insert(0, root)
        from tools import specs
        return len(specs.all_specs())
    except Exception:
        return -1


def measure(root=None, suites=None, timeout=600,
            with_registry: bool = True) -> dict:
    root = root or paths.ROOT
    if suites is None:
        suites = SUITES
    results, tp, tf = {}, 0, 0
    for s in suites:
        r = _run(s, root, timeout)
        if r is None:
            continue
        results[s] = r
        tp += r.get("passed", 0)
        tf += max(0, r.get("failed", 0))
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "suites": results,
        "passed": tp,
        "failed": tf,
        "tools": registry_size(root) if with_registry else -1,
        "root": root,
    }


def score(board: dict) -> float:
    """Higher is better; failures are heavily penalised."""
    return float(board.get("passed", 0)) - 5.0 * float(board.get("failed", 0))


def record(board: dict) -> dict:
    paths.append_jsonl("scoreboard.jsonl", board)
    paths.save_json("last_board.json", board)
    return board


def last() -> dict:
    return paths.load_json("last_board.json", {})


def history(limit=20) -> list:
    return paths.read_jsonl("scoreboard.jsonl", limit)


def compare(candidate: dict, baseline: dict) -> dict:
    cs, bs = score(candidate), score(baseline)
    return {"baseline": bs, "candidate": cs, "delta": cs - bs,
            "better": cs >= bs,
            "no_new_failures": candidate.get("failed", 0)
            <= baseline.get("failed", 0)}
