"""Per-domain serving presets consumed by the task-specialization router."""
from __future__ import annotations

import os

from coal_config import cfg

from . import placement

# name -> {desc, build(args) -> list, context_boost}
PRESETS = {
    "chat": {"desc": "current default config", "build": lambda: [
        "-ngl", str(cfg.model.gpu_layers)]},
    "cpu": {"desc": "pure CPU, no offload", "build": lambda: ["-ngl", "0"]},
    "moe_resident": {
        "desc": "dense+shared-expert on GPU0, experts CPU/mmap-pageable",
        "build": lambda: placement.placement_args()},
    "chip": {
        "desc": "moe_resident, tuned for RTL/coding loads",
        "build": lambda: placement.placement_args()},
}


def names() -> list:
    return sorted(PRESETS)


def resolve(name: str) -> list:
    p = PRESETS.get(name or "chat")
    if p is None:
        return []
    return [str(x) for x in p["build"]()]


def config_path() -> str:
    return getattr(cfg, "_path", None) or os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Programs", "Coal",
        "config.json")


def apply(name: str) -> dict:
    """Write `model.profile` + `model.extra_args` (+ gpu_layers) into
    config.json so the next server start uses the preset."""
    import json
    p = config_path()
    data = json.load(open(p, encoding="utf-8"))
    args = resolve(name)
    m = data.setdefault("model", {})
    m["profile"] = name
    m["extra_args"] = args
    m["gpu_layers"] = 8 if name == "chat" else 0   # placement via -ot, not -ngl
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return {"profile": name, "extra_args": args, "gpu_layers": m["gpu_layers"],
            "config": p}