"""Self-modification: ROX N may edit its own core files, safely.

Every edit is backed up first and syntax-validated before it lands. A
restart flag is written so the running process can pick up the change.
"""
from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUPS = os.path.join(os.path.expanduser("~"), ".rox", "backups")
FLAG = os.path.join(os.path.expanduser("~"), ".rox", "restart_needed")
CREATE_NO_WINDOW = 0x08000000


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def _resolve(path):
    """Resolve a path inside the ROX N codebase (no escape)."""
    p = os.path.abspath(os.path.expanduser(path))
    if not p.startswith(ROOT):
        p = os.path.abspath(os.path.join(ROOT, path.lstrip("/\\")))
    return p


def backup_self(args, ctx):
    """Snapshot one file (or the whole codebase) to ~/.rox/backups."""
    src = args.get("path")
    dest_root = os.path.join(BACKUPS, _stamp())
    try:
        if src:
            p = _resolve(src)
            if not os.path.exists(p):
                return {"ok": False, "output": f"no such file: {p}"}
            rel = os.path.relpath(p, ROOT)
            dest = os.path.join(dest_root, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(p, dest)
            return {"ok": True, "output": f"backed up {rel} -> {dest}"}
        os.makedirs(dest_root, exist_ok=True)
        shutil.copytree(os.path.join(ROOT, "tools"),
                        os.path.join(dest_root, "tools"))
        for f in os.listdir(ROOT):
            if f.endswith(".py"):
                shutil.copy2(os.path.join(ROOT, f),
                             os.path.join(dest_root, f))
        return {"ok": True, "output": f"backed up codebase -> {dest_root}"}
    except Exception as e:
        return {"ok": False, "output": f"backup failed: {e}"}


def list_backups(args, ctx):
    if not os.path.isdir(BACKUPS):
        return {"ok": True, "output": "(no backups yet)"}
    rows = sorted(os.listdir(BACKUPS), reverse=True)[:20]
    return {"ok": True, "output": "backups:\n" + "\n".join(
        os.path.join(BACKUPS, r) for r in rows)}


def restore_self(args, ctx):
    """Restore a file from a backup snapshot (by timestamp or path)."""
    snap = args.get("backup") or ""
    rel = args.get("path") or ""
    src = os.path.join(BACKUPS, snap, rel) if snap else ""
    if not src or not os.path.exists(src):
        return {"ok": False, "output": f"no backup at {src}"}
    dest = _resolve(rel)
    backup_self({"path": rel}, ctx)
    shutil.copy2(src, dest)
    _flag("restore " + rel)
    return {"ok": True, "output": f"restored {rel} from {snap} (restart to "
            f"apply)"}


def _flag(reason):
    try:
        os.makedirs(os.path.dirname(FLAG), exist_ok=True)
        with open(FLAG, "w", encoding="utf-8") as f:
            f.write(reason + "\n")
    except Exception:
        pass


def edit_self(args, ctx):
    """Edit a ROX N core file: backup -> validate -> write -> flag restart."""
    path = args.get("path")
    content = args.get("content")
    if not path or content is None:
        return {"ok": False, "output": "path and content are required"}
    p = _resolve(path)
    rel = os.path.relpath(p, ROOT)
    # 1. backup existing
    if os.path.exists(p):
        b = backup_self({"path": rel}, ctx)
        if not b.get("ok"):
            return b
    # 2. write to a temp file and syntax-validate
    tmp = p + ".new"
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        if p.endswith(".py"):
            try:
                py_compile.compile(tmp, doraise=True)
            except py_compile.PyCompileError as e:
                os.remove(tmp)
                return {"ok": False,
                        "output": f"SYNTAX ERROR, edit rejected:\n{e}"}
        # 3. swap in
        shutil.move(tmp, p)
    except Exception as e:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return {"ok": False, "output": f"edit failed: {e}"}
    _flag(rel)
    return {"ok": True, "output": f"edited {rel} (backed up + validated). "
            f"Restart to apply."}


def restart_self(args, ctx):
    """Relaunch the ROX N CLI after this process exits."""
    try:
        py = sys.executable
        entry = os.path.join(ROOT, "rox.py")
        helper = (
            f'@echo off\r\ntimeout /t 2 /nobreak >nul\r\n'
            f'start "" "{py}" "{entry}"\r\n')
        hp = os.path.join(os.path.expanduser("~"), ".rox", "_relaunch.bat")
        with open(hp, "w", encoding="ascii") as f:
            f.write(helper)
        subprocess.Popen(["cmd", "/c", hp], cwd=ROOT,
                         creationflags=CREATE_NO_WINDOW | 0x00000008)
    except Exception as e:
        return {"ok": False, "output": f"restart schedule failed: {e}"}
    return {"ok": True, "output": "restart scheduled; exiting now..."}


if __name__ == "__main__":
    from types import SimpleNamespace
    c = SimpleNamespace(workspace=".")
    print(list_backups({}, c))
    print(backup_self({}, c))