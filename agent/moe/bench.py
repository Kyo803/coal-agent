"""Bench: measure tokens/s, RSS and free RAM for a running/fresh server."""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
import urllib.request

from coal_config import cfg

BASE = cfg.base_url


def free_ram_gb() -> float:
    try:
        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        ms = MS()
        ms.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return round(ms.ullAvailPhys / 1e9, 1)
    except Exception:
        return -1.0


def server_rss_mb() -> int:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process llama-server -ErrorAction SilentlyContinue | "
             "Measure-Object WorkingSet64 -Sum).Sum"],
            creationflags=0x08000000, text=True, encoding="utf-8",
            errors="ignore")
        v = out.strip()
        return int(float(v)) // (1024 * 1024)
    except Exception:
        return -1


def _chat(n_predict=128, prompt="Write a short Python function that merges "
          "two sorted lists.", timeout=600):
    body = {"model": "local",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": n_predict, "temperature": 0.2, "stream": False}
    req = urllib.request.Request(BASE + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode())
    dt = time.time() - t0
    tok = out.get("usage", {}).get("completion_tokens", 0)
    return tok, dt, tok / dt if dt else 0.0


def measure(tag="", n_predict=128, runs=2, record=True) -> dict:
    tps, tot = [], 0.0
    for _ in range(max(1, runs)):
        tok, dt, t = _chat(n_predict)
        if tok:
            tps.append(t)
            tot += dt
    res = {
        "tag": tag or "measure",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tok_per_s": round(sum(tps) / len(tps), 2) if tps else 0.0,
        "latency_s": round(tot / max(1, len(tps)), 2),
        "server_rss_mb": server_rss_mb(),
        "free_ram_gb": free_ram_gb(),
    }
    if record:
        out_dir = os.path.join(os.path.dirname(cfg.model_path() or ""),
                               "variants")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "bench.jsonl"), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(res) + "\n")
    return res


def compare(a: dict, b: dict) -> dict:
    def d(k):
        try:
            return round(100 * (b[k] - a[k]) / abs(a[k] or 1), 1)
        except Exception:
            return None
    return {
        "tok_per_s": {"before": a.get("tok_per_s"), "after": b.get("tok_per_s"),
                      "delta_pct": d("tok_per_s")},
        "server_rss_mb": {"before": a.get("server_rss_mb"),
                          "after": b.get("server_rss_mb"),
                          "delta_pct": d("server_rss_mb")},
        "free_ram_gb": {"before": a.get("free_ram_gb"),
                        "after": b.get("free_ram_gb"),
                        "delta_gb": round(
                            (b.get("free_ram_gb", 0)
                             - a.get("free_ram_gb", 0)), 1)},
    }


if __name__ == "__main__":
    import sys
    import json as _j
    tag = sys.argv[1] if len(sys.argv) > 1 else "direct"
    print(_j.dumps(measure(tag=tag), indent=1))