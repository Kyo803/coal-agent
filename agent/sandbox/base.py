"""Low-level bridge between Windows and the Coal sandbox (WSL2 Ubuntu).

Everything in the sandbox package funnels through :func:`run`, which pipes
a bash script to ``wsl bash -s`` inside the isolated distro. This avoids
all Windows/quote escaping problems and needs no automount or interop.

The sandbox is the security boundary: the distro has no host filesystem
access (automount off), cannot run Windows binaries (interop off), and is
owned by ``coal`` (NOPASSWD sudo).
"""
from __future__ import annotations

import base64
import os
import shlex
import shutil
import subprocess

CREATE_NO_WINDOW = 0x08000000

DISTRO = os.environ.get("COAL_SANDBOX_DISTRO", "Ubuntu-24.04")
USER = os.environ.get("COAL_SANDBOX_USER", "coal")
WORKDIR = os.environ.get("COAL_SANDBOX_WORKDIR", "/home/coal/work")

_WSL = shutil.which("wsl") or shutil.which("wsl.exe") or "wsl"


def wsl_path() -> str:
    return _WSL


def shq(value) -> str:
    """POSIX single-quote a value (safe for use inside a bash script)."""
    return shlex.quote(str(value))


def b64(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.b64encode(data).decode("ascii")


def run(script: str, timeout: int = 300, root: bool = False,
        user: str | None = None, cwd: str | None = None,
        env: dict | None = None) -> dict:
    """Run a bash *script* inside the sandbox. Returns {rc, out, err, cmd}."""
    who = "root" if root else (user or USER)
    prelude = ""
    if cwd:
        prelude += f"cd {shq(cwd)} || exit 97\n"
    if env:
        for k, v in env.items():
            prelude += f"export {k}={shq(v)}\n"
    text = prelude + script
    args = [_WSL, "-d", DISTRO, "-u", who, "--", "bash", "-s"]
    try:
        p = subprocess.run(
            args, input=text, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=CREATE_NO_WINDOW)
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr,
                "cmd": script}
    except subprocess.TimeoutExpired as e:
        return {"rc": 124,
                "out": (e.stdout or "") if isinstance(e.stdout, str) else "",
                "err": f"timeout after {timeout}s",
                "cmd": script}


def _win_run(args, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=CREATE_NO_WINDOW)


def distro_list() -> list:
    """Return [(name, state, version)] for registered WSL distros."""
    try:
        p = _win_run([_WSL, "-l", "-v"])
        rows = []
        for line in p.stdout.splitlines():
            line = line.replace("\x00", "").strip()
            if not line or line.lower().startswith("name"):
                continue
            parts = line.replace("*", " ").split()
            if len(parts) >= 3:
                rows.append((parts[0], parts[1], parts[2]))
        return rows
    except Exception:
        return []


def distro_state(name: str = DISTRO) -> str:
    for n, state, _ in distro_list():
        if n.lower() == name.lower():
            return state
    return "unknown"


def terminate(name: str = DISTRO) -> dict:
    try:
        p = _win_run([_WSL, "--terminate", name], timeout=60)
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr}
    except Exception as e:
        return {"rc": 1, "out": "", "err": str(e)}
