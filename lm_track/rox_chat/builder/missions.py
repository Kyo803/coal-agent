"""Extreme mission catalog: load comprehensive project specs the builder
can consume contract-first (explicit file manifest + port contracts).

Missions live in `missions/*.json` and are driven by
`builder.build.generate_mission(name, ...)` or `rox.py --mission NAME`.
"""
from __future__ import annotations

import json
import os

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "missions")


def mission_dir() -> str:
    return DIR


def all_names() -> list:
    out = []
    if os.path.isdir(DIR):
        for fn in sorted(os.listdir(DIR)):
            if fn.endswith(".json") and fn not in ("queue.json",):
                out.append(fn[:-5])
    return out


def load(name: str) -> dict | None:
    p = os.path.join(DIR, name if name.endswith(".json") else name + ".json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def workspace_dir(name: str) -> str:
    return "/home/rox/work/" + name.lower()


def context(spec: dict) -> str:
    return (spec.get("description", "") + "\n\n"
            + spec.get("context", "")).strip()


def units(spec: dict) -> list:
    return spec.get("manifest", [])


def validate(spec: dict) -> tuple:
    if not spec or not spec.get("name"):
        return False, "missing name"
    man = units(spec)
    if not man:
        return False, "empty manifest"
    for u in man:
        if not u.get("path"):
            return False, "manifest unit missing path"
    return True, "ok"