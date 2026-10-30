"""Memory Mediator — arbitrates the 24 GB crunch across the 35B, Ollama
small models, and the sandbox, based on phase and measured RAM.

Advisory-first and safe: it can park Ollama models and report, and tells
schedulers when there is (or isn't) headroom. It never kills the 35B.
"""
from __future__ import annotations

import json
import urllib.request

from moe import bench


def snapshot() -> dict:
    from server_manager import ServerManager
    oll = []
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps",
                                    timeout=3) as r:
            d = json.loads(r.read().decode())
            oll = [m.get("model") for m in d.get("models", [])]
    except Exception:
        pass
    return {"free_ram_gb": bench.free_ram_gb(),
            "server_rss_mb": bench.server_rss_mb(),
            "ollama_loaded": oll,
            "server_up": ServerManager().health()}


def plan(phase: str = "chat") -> dict:
    s = snapshot()
    fr = s["free_ram_gb"]
    actions = []
    if fr < 1.5 and s.get("ollama_loaded"):
        actions.append({"action": "park_ollama",
                        "models": list(s["ollama_loaded"]),
                        "reason": f"free RAM {fr}GB < 1.5GB"})
    if phase == "build" and fr >= 3.0:
        actions.append({"action": "note", "msg": "headroom for sandbox build"})
    if fr >= 4.0:
        actions.append({"action": "note",
                        "msg": "headroom: context/budget could rise"})
    if fr < 1.0 and s.get("server_up"):
        actions.append({"action": "warn",
                        "msg": "RAM critical; prefer lower context or "
                               "park small models before new work"})
    return {"phase": phase, "snapshot": s, "actions": actions}


def apply(actions: list) -> dict:
    done = []
    for a in actions or []:
        if a.get("action") == "park_ollama":
            for m in a.get("models", []):
                try:
                    from learning import llm
                    llm.unload(m)
                    done.append(f"parked {m}")
                except Exception:
                    pass
    return {"done": done}


if __name__ == "__main__":
    import json as _j
    p = plan("chat")
    print(_j.dumps(p, indent=1))
    print("applied:", _j.dumps(apply(p["actions"])))