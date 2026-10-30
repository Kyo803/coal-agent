"""Run commands inside the sandbox."""
from __future__ import annotations

from . import base


def shell(command: str, timeout: int = 300, root: bool = False,
          cwd: str | None = None, env: dict | None = None) -> dict:
    """Run a shell command inside the sandbox. Returns {rc, out, err}."""
    return base.run(command, timeout=timeout, root=root, cwd=cwd, env=env)


def ok(command: str, timeout: int = 120, root: bool = False,
       cwd: str | None = None) -> bool:
    return shell(command, timeout=timeout, root=root, cwd=cwd)["rc"] == 0


def check(command: str, timeout: int = 120, root: bool = False,
          cwd: str | None = None) -> dict:
    r = shell(command, timeout=timeout, root=root, cwd=cwd)
    return {"ok": r["rc"] == 0, "output": (r["out"] or "") + (r["err"] or ""),
            "rc": r["rc"]}


def which(name: str) -> str | None:
    r = shell(f"command -v {base.shq(name)}")
    out = (r["out"] or "").strip()
    return out or None


def version(name: str, args: str = "--version") -> str | None:
    r = shell(f"{base.shq(name)} {args} 2>&1 | head -1")
    out = (r["out"] or "").strip()
    return out or None
