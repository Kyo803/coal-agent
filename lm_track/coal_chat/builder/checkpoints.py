"""Build checkpoints: save/resume the build state machine."""
from __future__ import annotations

import json
import os
import tempfile

from coal_config import cfg


def _dir(name: str) -> str:
    p = os.path.join(cfg.memory_root, "builds", name)
    os.makedirs(p, exist_ok=True)
    return p


def save(name: str, state: dict) -> str:
    p = os.path.join(_dir(name), "checkpoint.json")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    os.replace(tmp, p)
    return p


def load(name: str) -> dict:
    p = os.path.join(_dir(name), "checkpoint.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {}


def list_builds() -> list:
    root = os.path.join(cfg.memory_root, "builds")
    if not os.path.isdir(root):
        return []
    return sorted(os.listdir(root))


def clear(name: str) -> bool:
    p = os.path.join(_dir(name), "checkpoint.json")
    if os.path.exists(p):
        os.remove(p)
        return True
    return False
