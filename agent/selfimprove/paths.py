"""Paths + persistence for the self-improvement subsystem."""
from __future__ import annotations

import json
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Coal = os.path.join(os.path.expanduser("~"), ".coal")
HOME = os.path.join(Coal, "selfimprove")
BACKUPS = os.path.join(Coal, "backups")
FLAG = os.path.join(Coal, "restart_needed")
CREATE_NO_WINDOW = 0x08000000


def ensure():
    os.makedirs(HOME, exist_ok=True)
    return HOME


def path(name):
    ensure()
    return os.path.join(HOME, name)


def load_json(name, default):
    p = path(name)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(name, data):
    p = path(name)
    fd, tmp = tempfile.mkstemp(dir=HOME)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, p)


def append_jsonl(name, rec):
    with open(path(name), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_jsonl(name, limit=None):
    p = path(name)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out[-limit:] if limit else out
