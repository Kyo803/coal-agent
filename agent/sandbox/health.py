"""Sandbox health + introspection (OS, resources, tool versions)."""
from __future__ import annotations

from . import base

_INFO = r"""
echo "kernel:   $(uname -r)"
echo "arch:     $(uname -m)"
echo "cpus:     $(nproc)"
echo "mem:      $(free -h | awk '/Mem:/{print $2" total, "$7" avail"}')"
echo "disk:     $(df -h / | awk 'NR==2{print $2" size, "$4" avail"}')"
echo "systemd:  $(systemctl is-system-running 2>/dev/null || echo unknown)"
echo "uptime:   $(uptime -p)"
echo "user:     $(whoami)"
"""

_VERSION_CMDS = {
    "gcc": "gcc --version | head -1",
    "g++": "g++ --version | head -1",
    "clang": "clang --version | head -1",
    "make": "make --version | head -1",
    "cmake": "cmake --version | head -1",
    "python3": "python3 --version",
    "pip3": "pip3 --version | head -1",
    "node": "node --version",
    "npm": "npm --version",
    "git": "git --version",
    "iverilog": "iverilog -V 2>&1 | head -1",
    "verilator": "verilator --version",
    "go": "go version",
    "cargo": "cargo --version",
    "sqlite3": "sqlite3 --version",
    "rg": "rg --version | head -1",
    "tmux": "tmux -V",
}


def info() -> str:
    r = base.run(_INFO)
    return r["out"] or r["err"]


def versions() -> dict:
    script = ""
    for name, cmd in _VERSION_CMDS.items():
        script += (f"if command -v {base.shq(name.split()[0])} >/dev/null 2>&1;"
                   f" then echo \"{name}: $({cmd} 2>&1 | head -1)\";"
                   f" else echo \"{name}: (missing)\"; fi\n")
    r = base.run(script)
    out = {}
    for line in (r["out"] or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def free_ram_mb() -> int:
    r = base.run("free -m | awk '/Mem:/{print $7}'")
    try:
        return int((r["out"] or "0").strip())
    except Exception:
        return -1


def snapshot() -> dict:
    return {"info": info(), "versions": versions(),
            "free_ram_mb": free_ram_mb()}
