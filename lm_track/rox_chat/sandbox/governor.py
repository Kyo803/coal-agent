"""Resource governor: keep host + sandbox + models inside RAM/CPU budget.

Phase 1 is informational + a controlled WSL memory cap setter. Later phases
use :func:`park_models` / :func:`resume_models` to free RAM before heavy
sandbox builds.
"""
from __future__ import annotations

import ctypes
import os
import re

from . import base, session


def host_free_ram_gb() -> float:
    try:
        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        ms = MS()
        ms.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return round(ms.ullAvailPhys / 1e9, 1)
    except Exception:
        return -1.0


def wsl_memory_limit() -> str | None:
    p = os.path.join(os.path.expanduser("~"), ".wslconfig")
    if not os.path.exists(p):
        return None
    try:
        txt = open(p, encoding="utf-8").read()
        m = re.search(r"^\s*memory\s*=\s*(\S+)", txt, re.M)
        return m.group(1) if m else None
    except Exception:
        return None


def set_wsl_memory(size: str, processors: int | None = None) -> str:
    """Rewrite ~/.wslconfig (applies after `wsl --shutdown`)."""
    p = os.path.join(os.path.expanduser("~"), ".wslconfig")
    lines = ["[wsl2]", f"memory={size}"]
    if processors:
        lines.append(f"processors={processors}")
    lines.append("swap=2GB")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return p


def summary() -> dict:
    st = session.status()
    return {
        "host_free_ram_gb": host_free_ram_gb(),
        "wsl_memory_limit": wsl_memory_limit(),
        "sandbox_running": st.get("running"),
        "sandbox_state": st.get("state"),
        "sandbox_distro": st.get("distro"),
    }


def restart_wsl() -> dict:
    try:
        r = base._win_run([base.wsl_path(), "--shutdown"], timeout=60)
        return {"rc": r.returncode, "out": r.stdout, "err": r.stderr}
    except Exception as e:
        return {"rc": 1, "out": "", "err": str(e)}
