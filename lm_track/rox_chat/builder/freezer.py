"""Freezer: verified units are frozen by content hash.

A frozen unit is not regenerated unless its own interface (exports)
changes — this stops the repair loop from thrashing already-good files.
"""
from __future__ import annotations

import hashlib
import json
import os

from rox_config import cfg


def _dir(name: str) -> str:
    p = os.path.join(cfg.memory_root, "builds", name)
    os.makedirs(p, exist_ok=True)
    return p


def sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


class Freezer:
    def __init__(self, name: str):
        self.name = name
        self.file = os.path.join(_dir(name), "frozen.json")
        self.data = {}
        if os.path.exists(self.file):
            try:
                self.data = json.load(open(self.file, encoding="utf-8"))
            except Exception:
                self.data = {}

    def save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1)

    def is_frozen(self, rel: str, text: str, exports=None) -> bool:
        rec = self.data.get(rel)
        if not rec or rec.get("hash") != sha(text):
            return False
        if exports is not None and sorted(exports) != sorted(
                rec.get("exports", [])):
            return False
        return True

    def freeze(self, rel: str, text: str, exports=None):
        self.data[rel] = {"hash": sha(text),
                          "exports": sorted(exports or [])}
        self.save()

    def unfreeze(self, rel: str):
        self.data.pop(rel, None)
        self.save()

    def frozen_units(self) -> list:
        return sorted(self.data)
