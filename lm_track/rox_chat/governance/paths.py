"""Persistence for governance/telemetry."""
from __future__ import annotations

import json
import os
import tempfile

from rox_config import cfg


def root() -> str:
    p = os.path.join(cfg.memory_root, "governance")
    os.makedirs(p, exist_ok=True)
    return p


def path(name: str) -> str:
    return os.path.join(root(), name)


def load_json(name: str, default):
    p = path(name)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(name: str, data) -> None:
    p = path(name)
    fd, tmp = tempfile.mkstemp(dir=root())
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, p)


def append_jsonl(name: str, rec: dict) -> None:
    with open(path(name), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_jsonl(name: str, limit: int | None = None) -> list:
    p = path(name)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out[-limit:] if limit else out
