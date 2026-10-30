"""Health: watchdogs for the model server, Ollama, and the sandbox."""
from __future__ import annotations

import urllib.request

from sandbox import session

from . import resource


def _http_ok(url: str, timeout: int = 3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


def snapshot() -> dict:
    return {
        "server_35b": _http_ok("http://127.0.0.1:1234/v1/models"),
        "ollama": _http_ok("http://127.0.0.1:11434/api/tags"),
        "sandbox": session.is_running(),
        "host_free_ram_gb": resource.host_free_ram_gb(),
        "wsl_memory": resource.wsl_memory_limit(),
    }


def ok() -> bool:
    s = snapshot()
    return bool(s["server_35b"] or s["sandbox"])
