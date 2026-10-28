"""Persistence helpers for the knowledge subsystem."""
from __future__ import annotations

import json
import os
import tempfile

from rox_config import cfg


def root() -> str:
    p = os.path.join(cfg.memory_root, "knowledge")
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


def skills_root() -> str:
    p = os.path.join(cfg.memory_root, "skills")
    os.makedirs(p, exist_ok=True)
    return p
