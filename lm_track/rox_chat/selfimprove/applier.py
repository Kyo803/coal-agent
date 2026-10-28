"""Applier: land an approved change on the live self (backup + validate).

Currently supports low-risk changes (seeding the learning frontier) and
file content changes (backed up, syntax-checked, restart flagged).
"""
from __future__ import annotations

import json
import os
import py_compile
import time

from rox_config import cfg

from . import backup, paths


def _flag(reason: str) -> None:
    try:
        os.makedirs(os.path.dirname(paths.FLAG), exist_ok=True)
        with open(paths.FLAG, "w", encoding="utf-8") as f:
            f.write(reason + "\n")
    except Exception:
        pass


def _record(rec: dict) -> dict:
    rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    paths.append_jsonl("applied.jsonl", rec)
    return rec


def apply(change: dict, dry_run: bool = False) -> dict:
    if dry_run:
        return {"ok": True, "dry_run": True}
    kind = change.get("kind")
    if kind == "seed":
        return _apply_seed(change)
    if kind in ("code", "prompt"):
        if change.get("content") is None:
            return {"ok": False, "reason": "needs review before apply"}
        return _apply_file(change["target"], change["content"])
    return {"ok": False, "reason": f"unknown change kind: {kind}"}


def _apply_seed(change: dict) -> dict:
    p = getattr(cfg, "_path", None)
    if not p or not os.path.exists(p):
        return {"ok": False, "reason": "config path unavailable"}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"ok": False, "reason": f"config read failed: {e}"}
    learning = data.setdefault("learning", {})
    seeds = learning.setdefault("seed_topics", [])
    added = [t for t in change.get("topics", []) if t and t not in seeds]
    if not added:
        return {"ok": False, "reason": "no new topics"}
    backup.backup_target("config:seed_topics")
    seeds.extend(added)
    learning["seed_topics"] = seeds
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _record({"kind": "seed", "added": added, "target": p})
    return {"ok": True, "added": added, "config": p}


def _apply_file(rel: str, content: str) -> dict:
    dest = os.path.join(paths.ROOT, rel)
    backup.backup_file(rel)
    tmp = dest + ".new"
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        if dest.endswith(".py"):
            try:
                py_compile.compile(tmp, doraise=True)
            except py_compile.PyCompileError as e:
                os.remove(tmp)
                return {"ok": False, "reason": f"syntax error: {e}"}
        os.replace(tmp, dest)
    except Exception as e:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return {"ok": False, "reason": str(e)}
    _flag(f"selfimprove apply {rel}")
    _record({"kind": "file", "target": rel})
    return {"ok": True, "target": rel, "restart": True}
