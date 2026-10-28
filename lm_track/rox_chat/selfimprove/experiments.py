"""Experiments: test a change in an isolated copy before it touches the self.

Copies the runtime core to a temp dir, applies the change there, runs the
relevant suites, and compares the score against the last recorded board.
The live tree is never modified by an experiment.
"""
from __future__ import annotations

import os
import shutil
import tempfile

from . import paths, scoreboard

CORE = ["tools", "board", "memory", "learning", "sandbox", "project",
        "selfimprove", "governance", "autonomy", "finetune", "knowledge"]


def _copy_core(dest: str, root: str) -> None:
    for d in CORE:
        s = os.path.join(root, d)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(dest, d),
                            ignore=shutil.ignore_patterns("__pycache__",
                                                          "*.pyc"))
    for fn in os.listdir(root):
        if fn.endswith(".py"):
            try:
                shutil.copy2(os.path.join(root, fn),
                             os.path.join(dest, fn))
            except Exception:
                pass


def _apply_to_tmp(change: dict, dest: str) -> None:
    if change.get("kind") in ("code", "prompt") and \
            change.get("content") is not None:
        rel = change.get("target", "")
        if not rel:
            return
        p = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(change["content"])


def run(change: dict, root: str | None = None,
        suites=("test_tools", "test_learning"), timeout: int = 900) -> dict:
    root = root or paths.ROOT
    tmp = tempfile.mkdtemp(prefix="rox_exp_")
    try:
        _copy_core(tmp, root)
        _apply_to_tmp(change, tmp)
        board = scoreboard.measure(root=tmp, suites=list(suites),
                                   timeout=timeout, with_registry=False)
        base = scoreboard.last()
        if base and base.get("suites"):
            cmp = scoreboard.compare(board, base)
        else:
            cmp = {"baseline": 0, "candidate": scoreboard.score(board),
                   "delta": 0, "better": board.get("failed", 0) == 0,
                   "no_new_failures": board.get("failed", 0) == 0}
        return {"passed": bool(cmp.get("better")
                               and cmp.get("no_new_failures")),
                "board": board, "compare": cmp}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
