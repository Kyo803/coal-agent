"""Toolchain discovery — make external compilers usable on this PC.

ROX N shells out to native tools (iverilog, vvp, gtkwave, blender, node,
git...). On Windows some of them live in non-standard places or need their
own bin directory on PATH so they can find sibling DLLs (MSYS2's iverilog
is the classic case). This module finds them and fixes PATH once, early.
"""
from __future__ import annotations

import os
import shutil

# Directories that may hold native toolchains, in priority order.
_TOOL_DIRS = [
    r"C:\msys64\ucrt64\bin",
    r"C:\msys64\mingw64\bin",
    r"C:\msys64\usr\bin",
    r"C:\iverilog\bin",
    r"C:\Program Files\Blender Foundation\Blender 5.2",
    r"C:\Program Files\Blender Foundation\Blender 4.2",
    r"C:\Program Files\Blender Foundation\Blender 4.1",
]


def ensure_paths() -> list:
    """Prepend any existing toolchain dirs to PATH. Returns ones added."""
    added = []
    path = os.environ.get("PATH", "")
    parts = path.split(os.pathsep)
    low = [p.rstrip("\\/").lower() for p in parts]
    for d in _TOOL_DIRS:
        if os.path.isdir(d) and d.rstrip("\\/").lower() not in low:
            parts.insert(0, d)
            added.append(d)
    if added:
        os.environ["PATH"] = os.pathsep.join(parts)
    return added


def find(name: str):
    """Locate an executable by name across PATH + known tool dirs."""
    p = shutil.which(name)
    if p:
        return p
    for d in _TOOL_DIRS:
        for ext in ("", ".exe"):
            cand = os.path.join(d, name + ext)
            if os.path.isfile(cand):
                return cand
    return None


def has_iverilog() -> bool:
    return bool(find("iverilog"))


def report() -> dict:
    ensure_paths()
    return {
        "iverilog": find("iverilog"),
        "vvp": find("vvp"),
        "gtkwave": find("gtkwave"),
        "blender": find("blender"),
        "node": find("node"),
        "git": find("git"),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(report(), indent=1))
