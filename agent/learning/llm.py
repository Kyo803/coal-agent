"""Small-model calls for the learning subsystem (Ollama, CPU-only).

The learning brain runs background work on a small model (default
`coaln-3b`) so it never competes with the 35B for VRAM. All calls are
guarded: if Ollama is unavailable, callers fall back to heuristics.
"""
from __future__ import annotations

import json
import re
import urllib.request

from memory.embed import ensure_ollama
from coal_config import cfg


def _section():
    return cfg.get("learning", {}) or {}


def model_name() -> str:
    return _section().get("model") or (cfg.get("board", {}) or {}).get(
        "model", "coaln-3b")


def _url() -> str:
    return (_section().get("ollama_url") or cfg.memory.ollama_url).rstrip("/")


def num_ctx() -> int:
    return int(_section().get("num_ctx", 4096))


def available() -> bool:
    import os
    if os.environ.get("COAL_LEARN_NO_LLM"):
        return False
    return ensure_ollama()


def chat(messages, model=None, fmt=None, temperature=0.3,
         keep_alive="10m", timeout=180) -> str:
    """Return the assistant text, or '' on any failure."""
    payload = {
        "model": model or model_name(),
        "messages": messages,
        "stream": False,
        "keep_alive": keep_alive,
        "options": {"temperature": temperature, "num_ctx": num_ctx(),
                    "num_thread": int(_section().get("num_thread", 4))},
    }
    if fmt:
        payload["format"] = fmt
    try:
        req = urllib.request.Request(
            _url() + "/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return ((d.get("message") or {}).get("content") or "").strip()
    except Exception:
        return ""


def json_chat(messages, **kw):
    """Call the model expecting JSON; return dict/list or None."""
    text = chat(messages, fmt="json", **kw)
    if not text:
        return None
    m = re.search(r"[\{\[].*[\}\]]", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def unload(model=None) -> None:
    """Ask Ollama to unload the model (free RAM)."""
    try:
        payload = {"model": model or model_name(), "keep_alive": 0}
        req = urllib.request.Request(
            _url() + "/api/generate", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass
