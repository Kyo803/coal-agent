"""Rollback: restore the previous good self from a snapshot."""
from __future__ import annotations

import os
import shutil

from coal_config import cfg

from . import backup, paths


def _find(rel: str, snapshots: list) -> tuple:
    for s in snapshots:
        c = os.path.join(paths.BACKUPS, s, rel)
        if os.path.exists(c):
            return s, c
    return None, None


def restore_file(rel: str, snapshot: str | None = None) -> dict:
    snaps = ([snapshot] if snapshot else []) + backup.list_snapshots(50)
    snap, src = _find(rel, [s for s in snaps if s])
    if not src:
        return {"ok": False, "reason": f"{rel} not found in backups"}
    backup.backup_file(rel)
    dest = os.path.join(paths.ROOT, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)
    return {"ok": True, "restored": rel, "from": snap}


def restore_config(snapshot: str | None = None) -> dict:
    p = getattr(cfg, "_path", None)
    if not p:
        return {"ok": False, "reason": "config path unavailable"}
    base = os.path.basename(p)
    snap, src = _find(base, [s for s in ([snapshot] if snapshot else [])]
                      + backup.list_snapshots(50))
    if not src:
        return {"ok": False, "reason": "no config snapshot"}
    shutil.copy2(p, p + ".pre_rollback")
    shutil.copy2(src, p)
    return {"ok": True, "restored": base, "from": snap}


def list_snapshots(limit: int = 20) -> list:
    return backup.list_snapshots(limit)
