"""Resource governor: keep the 35B, the small models, and the sandbox
inside the machine's RAM/CPU budget."""
from __future__ import annotations

from sandbox import governor as sb_gov


def host_free_ram_gb() -> float:
    return sb_gov.host_free_ram_gb()


def wsl_memory_limit():
    return sb_gov.wsl_memory_limit()


def can_run_heavy(min_free_gb: float = 3.0) -> bool:
    free = host_free_ram_gb()
    return free < 0 or free >= min_free_gb


def park_35b() -> bool:
    try:
        from server_manager import ServerManager
        return ServerManager().stop()
    except Exception:
        return False


def resume_35b() -> bool:
    try:
        from server_manager import ServerManager
        return ServerManager().ensure()
    except Exception:
        return False


def summary() -> dict:
    s = sb_gov.summary()
    s["can_run_heavy"] = can_run_heavy()
    return s
