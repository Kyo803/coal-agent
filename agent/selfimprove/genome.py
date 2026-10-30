"""Genome: a versioned fingerprint of Coal's current self.

Hashes the runtime core (tools, board, memory, learning, sandbox, project,
and the top-level modules). Each applied change produces a new generation
that can be diffed and rolled back.
"""
from __future__ import annotations

import hashlib
import os

from . import paths

CORE_DIRS = ["tools", "board", "memory", "learning", "sandbox", "project"]
SKIP = {"__pycache__", ".git", "node_modules", ".venv", "venv", "dist",
        "build"}


def _sha(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
    except Exception:
        return ""
    return h.hexdigest()


def scan(root: str | None = None) -> dict:
    root = root or paths.ROOT
    files = {}
    # top-level .py modules
    for fn in os.listdir(root):
        p = os.path.join(root, fn)
        if fn.endswith(".py") and os.path.isfile(p):
            files[fn] = _sha(p)
    # core packages
    for d in CORE_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in SKIP]
            for fn in filenames:
                if fn.endswith((".py", ".html", ".json")):
                    p = os.path.join(dirpath, fn)
                    rel = os.path.relpath(p, root).replace("\\", "/")
                    files[rel] = _sha(p)
    return files


def genome_id(files: dict) -> str:
    h = hashlib.sha256()
    for k in sorted(files):
        h.update(k.encode())
        h.update(files[k].encode())
    return h.hexdigest()[:16]


def snapshot(root: str | None = None) -> dict:
    files = scan(root)
    import time
    return {"id": genome_id(files), "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "files": files, "count": len(files)}


def record(gen: dict | None = None) -> dict:
    gen = gen or snapshot()
    cur = paths.load_json("current_gen.json", {})
    n = int(cur.get("generation", 0)) + 1
    gen["generation"] = n
    paths.save_json("current_gen.json", gen)
    paths.append_jsonl("generations.jsonl", {
        "generation": n, "id": gen["id"], "ts": gen["ts"],
        "count": gen["count"]})
    return gen


def current() -> dict:
    return paths.load_json("current_gen.json", {})


def diff(a: dict, b: dict) -> dict:
    af, bf = a.get("files", {}), b.get("files", {})
    added = [k for k in bf if k not in af]
    removed = [k for k in af if k not in bf]
    changed = [k for k in af if k in bf and af[k] != bf[k]]
    return {"added": added, "removed": removed, "changed": changed,
            "n_changed": len(added) + len(removed) + len(changed)}
