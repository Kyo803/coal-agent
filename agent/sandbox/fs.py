"""File operations inside the sandbox (host<->sandbox by value).

No shared mount is used: reads stream the file out as base64, writes
stream it in as base64. This works with automount disabled.
"""
from __future__ import annotations

import posixpath

from . import base


def exists(path: str) -> bool:
    return base.run(f"test -e {base.shq(path)}")["rc"] == 0


def read(path: str, binary: bool = False):
    if binary:
        r = base.run(f"base64 -w0 -- {base.shq(path)}")
        if r["rc"] != 0:
            return None
        import base64 as _b
        return _b.b64decode(r["out"].strip())
    r = base.run(f"cat -- {base.shq(path)}")
    return r["out"] if r["rc"] == 0 else None


def read_text(path: str) -> str:
    return read(path, binary=False) or ""


def write(path: str, content, root: bool = False, mode: str | None = None):
    parent = posixpath.dirname(path) or "."
    data = base.b64(content)
    modecmd = f" && chmod {base.shq(mode)} -- {base.shq(path)}" if mode else ""
    script = (f"mkdir -p -- {base.shq(parent)} && "
              f"printf %s {base.shq(data)} | base64 -d > {base.shq(path)}"
              f"{modecmd}")
    r = base.run(script, root=root)
    return r["rc"] == 0


def append(path: str, content, root: bool = False):
    data = base.b64(content)
    script = (f"printf %s {base.shq(data)} | base64 -d >> {base.shq(path)}")
    return base.run(script, root=root)["rc"] == 0


def edit(path: str, old: str, new: str):
    """Exact-string replace inside a sandbox file."""
    content = read_text(path)
    if old not in content:
        return False
    write(path, content.replace(old, new, 1))
    return True


def mkdir(path: str, root: bool = False):
    return base.run(f"mkdir -p -- {base.shq(path)}", root=root)["rc"] == 0


def listdir(path: str = "."):
    r = base.run(f"ls -la -- {base.shq(path)} 2>&1")
    return r["out"] if r["rc"] == 0 else r["err"]


def move(src: str, dst: str, root: bool = False):
    r = base.run(f"mkdir -p -- {base.shq(posixpath.dirname(dst))} && "
                 f"mv -- {base.shq(src)} {base.shq(dst)}", root=root)
    return r["rc"] == 0


def copy(src: str, dst: str, root: bool = False):
    r = base.run(f"mkdir -p -- {base.shq(posixpath.dirname(dst))} && "
                 f"cp -r -- {base.shq(src)} {base.shq(dst)}", root=root)
    return r["rc"] == 0


def remove(path: str, recursive: bool = False, root: bool = False):
    flag = "-rf" if recursive else "-f"
    return base.run(f"rm {flag} -- {base.shq(path)}", root=root)["rc"] == 0


def stat(path: str) -> str:
    r = base.run(f"stat -- {base.shq(path)} 2>&1")
    return r["out"] if r["rc"] == 0 else r["err"]
