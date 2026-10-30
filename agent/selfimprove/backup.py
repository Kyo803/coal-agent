"""Backup: snapshot files/generations before a change lands."""
from __future__ import annotations

import os
import shutil
import time

from coal_config import cfg

from . import genome, paths


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def backup_file(rel: str, root: str | None = None) -> str | None:
    root = root or paths.ROOT
    src = os.path.join(root, rel)
    if not os.path.isfile(src):
        return None
    dest = os.path.join(paths.BACKUPS, stamp(), rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def backup_target(target: str) -> str | None:
    """target may be 'config:...' (the running config) or a repo-relative
    file path."""
    if target.startswith("config:") or target == "persona":
        p = getattr(cfg, "_path", None)
        if p and os.path.exists(p):
            dest = os.path.join(paths.BACKUPS, stamp(),
                                os.path.basename(p))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(p, dest)
            return dest
        return None
    return backup_file(target)


def snapshot_genome() -> dict:
    return genome.record()


def list_snapshots(limit: int = 20) -> list:
    if not os.path.isdir(paths.BACKUPS):
        return []
    return sorted(os.listdir(paths.BACKUPS), reverse=True)[:limit]
