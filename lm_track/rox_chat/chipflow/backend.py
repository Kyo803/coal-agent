"""Tool backend: native Windows, WSL, or YoWASP (WebAssembly).

Why this exists: this machine enforces WDAC/VBS + Smart App Control, which
blocks unsigned Windows binaries (ivl.exe, verilator, native yosys,
nextpnr). Linux binaries inside WSL are not subject to Windows code
integrity, so when a WSL distro is present we run the *real* toolchain
there. Otherwise we fall back to YoWASP yosys (WASM), which always works
but has no simulator and no ABC.

Selection is automatic and cached:
    wsl      -> iverilog, verilator, yosys(+abc), nextpnr, gtkwave
    native   -> only if the exe actually runs (rare on this box)
    wasm     -> yosys only (synth/formal/equiv)
"""
from __future__ import annotations

import os
import shutil
import subprocess

_TOOL_DIRS = [r"C:\msys64\ucrt64\bin", r"C:\msys64\mingw64\bin",
              r"C:\iverilog\bin"]

_CACHE = {}


def _wsl_exe():
    return shutil.which("wsl") or r"C:\Windows\System32\wsl.exe"


def wsl_distro():
    """First registered WSL distro, or None."""
    if "distro" in _CACHE:
        return _CACHE["distro"]
    d = None
    try:
        r = subprocess.run([_wsl_exe(), "-l", "-q"], capture_output=True,
                           text=True, timeout=20, creationflags=0x08000000,
                           encoding="utf-8", errors="replace")
        names = [x.strip().replace("\x00", "")
                 for x in (r.stdout or "").splitlines()]
        names = [n for n in names if n]
        if names:
            pref = [n for n in names if "ROX" in n.upper()]
            d = (pref or names)[0]
    except Exception:
        d = None
    _CACHE["distro"] = d
    return d


def to_wsl_path(p: str) -> str:
    p = os.path.abspath(p)
    drive, rest = os.path.splitdrive(p)
    rest = rest.replace("\\", "/")
    if not drive:
        return rest
    return f"/mnt/{drive[0].lower()}{rest}"


def wsl_tool(name: str):
    """Path/command of a tool inside WSL, or None."""
    key = "wsl:" + name
    if key in _CACHE:
        return _CACHE[key]
    d = wsl_distro()
    if not d:
        _CACHE[key] = None
        return None
    try:
        r = subprocess.run(
            [_wsl_exe(), "-d", d, "--", "bash", "-lc",
             f"command -v {name}"],
            capture_output=True, text=True, timeout=30,
            creationflags=0x08000000, encoding="utf-8", errors="replace")
        out = (r.stdout or "").strip()
        _CACHE[key] = out.splitlines()[0] if r.returncode == 0 and out else None
    except Exception:
        _CACHE[key] = None
    return _CACHE[key]


def wsl_available() -> bool:
    return bool(wsl_distro())


def wsl_run(cmd, cwd=None, timeout=900, env=None):
    """Run a command inside WSL, with `cwd` mapped to /mnt/<drive>/..."""
    d = wsl_distro()
    if not d:
        return {"ok": False, "rc": -3, "out": "no WSL distro",
                "cmd": [str(c) for c in cmd]}
    wpath = to_wsl_path(cwd) if cwd else "~"
    if isinstance(cmd, (list, tuple)):
        parts = []
        for c in cmd:
            c = str(c)
            parts.append("'" + c.replace("'", "'\\''") + "'"
                         if (" " in c or c.startswith("-") is False and
                             any(ch in c for ch in "()[]$`\"'")) else c)
        cmdline = " ".join(parts)
    else:
        cmdline = str(cmd)
    script = f"cd '{wpath}' 2>/dev/null || cd ~; {cmdline}"
    try:
        r = subprocess.run(
            [_wsl_exe(), "-d", d, "--", "bash", "-lc", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=0x08000000, encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        return {"ok": r.returncode == 0, "rc": r.returncode, "out": out,
                "cmd": [str(c) for c in cmd]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "rc": -1, "out": f"timeout after {timeout}s",
                "cmd": [str(c) for c in cmd]}
    except Exception as ex:
        return {"ok": False, "rc": -2, "out": str(ex),
                "cmd": [str(c) for c in cmd]}


# ---------------------------------------------------------------- native
def _runs(path, arg="-V"):
    try:
        r = subprocess.run([path, arg], capture_output=True, text=True,
                           timeout=40, encoding="utf-8", errors="replace")
        return r.returncode == 0
    except Exception:
        return False


def native_tool(name: str):
    key = "native:" + name
    if key in _CACHE:
        return _CACHE[key]
    p = shutil.which(name)
    if not p:
        for d in _TOOL_DIRS:
            for ext in ("", ".exe"):
                c = os.path.join(d, name + ext)
                if os.path.isfile(c):
                    p = c
                    break
            if p:
                break
    if p and not _runs(p):
        p = None
    _CACHE[key] = p
    return p


def yowasp(name="yosys"):
    key = "yowasp:" + name
    if key in _CACHE:
        return _CACHE[key]
    import sys
    cands = [shutil.which("yowasp-" + name),
             os.path.join(os.path.dirname(sys.executable), "Scripts",
                          f"yowasp-{name}.exe"),
             os.path.join(os.path.dirname(sys.executable), "Scripts",
                          f"yowasp-{name}")]
    p = None
    for c in cands:
        if c and os.path.isfile(c) and _runs(c):
            p = c
            break
    _CACHE[key] = p
    return p


# ---------------------------------------------------------------- summary
def report() -> dict:
    d = wsl_distro()
    tools = {}
    if d:
        for t in ("iverilog", "vvp", "verilator", "yosys", "nextpnr-ice40",
                  "gtkwave", "abc"):
            tools[t] = bool(wsl_tool(t))
    return {
        "backend": "wsl" if d else ("native" if native_tool("yosys")
                                    else "wasm"),
        "wsl_distro": d,
        "wsl_tools": tools,
        "yowasp_yosys": yowasp("yosys"),
        "native_yosys": native_tool("yosys"),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(report(), indent=1))
