"""Batch chip builder — ROX N designs a whole corpus on its own.

Safety (this machine has crashed before):
  * one chip at a time, never parallel
  * refuses to run below a free-RAM floor
  * BelowNormal process priority
  * per-chip timeout, bounded repairs
  * STOP file + resumable results (skips chips already passed)
  * writes JSONL + a human report

    from chipflow.batch import default_corpus, run_batch
    run_batch(limit=50)
"""
from __future__ import annotations

import json
import os
import time

from .build import build as _build_one
from . import model as M

OUT = os.path.join(os.path.expanduser("~"), ".rox", "work", "chips", "_batch")
RESULTS = os.path.join(OUT, "results.jsonl")
STOP = os.path.join(OUT, "STOP")
FLOOR_GB = float(os.environ.get("ROX_BATCH_FLOOR_GB", "6.0"))


def default_corpus() -> list:
    """50 designs: 42 deterministic (perfect by construction) + 8 novel
    (the model composes, then must pass the same gate)."""
    c = []

    def add(name, kind, **params):
        c.append({"name": name, "kind": kind, "params": params})

    for w in (4, 8, 12, 16, 24, 32):
        add(f"counter{w}", "counter", width=w)
    for w in (4, 8, 12, 16):
        add(f"cmp{w}", "comparator", width=w)
    for w in (8, 16, 32):
        add(f"shiftreg{w}", "shiftreg", width=w)
    for w in (8, 10, 12, 16):
        add(f"pwm{w}", "pwm", width=w)
    for cpb in (8, 16, 32):
        add(f"uart_tx_cpb{cpb}", "uart_tx", clks_per_bit=cpb)
    for cpb in (8, 16, 32):
        add(f"uart_rx_cpb{cpb}", "uart_rx", clks_per_bit=cpb)
    for w, d in ((8, 4), (8, 8), (8, 16), (16, 8), (16, 16), (32, 16)):
        add(f"fifo{w}x{d}", "fifo", width=w, depth=d)
    for w, d in ((8, 4), (8, 8), (16, 8), (32, 16)):
        add(f"regfile{w}x{d}", "regfile", width=w, depth=d)
    for dv in (2, 4, 8, 16):
        add(f"clkdiv{dv}", "clkdiv", div=dv)
    add("alu4", "alu4")
    add("fsm3", "fsm3")
    add("vga640", "vga_timing")

    # novel specs for the model (must still pass the gate)
    novel = [
        ("bcd_counter", "a 4-bit BCD counter (0-9, wraps to 0) with a carry "
                        "output, synchronous reset"),
        ("seg7", "a 7-segment decoder: input [3:0] hex, output [6:0] seg "
                 "(active low)"),
        ("prio_enc8", "an 8-to-3 priority encoder with a valid output; the "
                      "highest set bit wins"),
        ("addsub4", "a 4-bit adder/subtractor with a mode input, carry and "
                    "overflow outputs"),
        ("gray4", "a 4-bit binary to Gray code converter (combinational)"),
        ("onehot_arb", "a 4-way round-robin arbiter with request[3:0] and "
                       "grant[3:0], one-hot grant"),
        ("debounce8", "a button debouncer with an 8-bit counter and a clean "
                      "registered output"),
        ("spi_master", "a minimal SPI master, mode 0, 8-bit, with start/busy, "
                       "sclk, mosi and a received byte"),
        ("mult4", "a 4x4 unsigned multiplier with an 8-bit product "
                  "(combinational)"),
        ("uart_loopback_soc", "a UART loopback chip: receive a byte into a "
                              "FIFO and transmit it back"),
    ]
    for n, spec in novel:
        c.append({"name": n, "spec": spec, "kind": None, "params": {}})
    return c[:50]


def _low_priority():
    try:
        import ctypes
        h = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(h, 0x00004000)  # below normal
    except Exception:
        pass


def _passed():
    done = set()
    try:
        with open(RESULTS, encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if r.get("ok"):
                    done.add(r.get("name"))
    except Exception:
        pass
    return done


def _record(r):
    os.makedirs(OUT, exist_ok=True)
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(r) + "\n")


def _stop():
    return os.path.exists(STOP)


def run_batch(corpus=None, limit=50, resume=True, log=print) -> dict:
    _low_priority()
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(STOP):
        os.remove(STOP)
    corpus = (corpus or default_corpus())[:limit]
    done = _passed() if resume else set()
    rows = []
    t_start = time.time()
    for i, item in enumerate(corpus, 1):
        name = item["name"]
        if name in done:
            log(f"[{i:2d}/{len(corpus)}] {name}: already passed, skip")
            continue
        if _stop():
            log("STOP file found -> stopping batch")
            break
        free = M.free_ram_gb()
        tries = 0
        while free < FLOOR_GB and tries < 6:
            log(f"RAM low ({free:.1f} GB < {FLOOR_GB}) -> waiting 30s "
                f"({tries+1}/6)")
            time.sleep(30)
            tries += 1
            free = M.free_ram_gb()
        if free < FLOOR_GB:
            log("RAM still low -> stopping batch")
            break
        t0 = time.time()
        try:
            rep = _build_one(name, spec=item.get("spec") or "",
                             kind=item.get("kind"),
                             params=item.get("params") or {},
                             max_repairs=1, make_views=False)
        except Exception as e:
            rep = {"ok": False, "design": name, "stages": {},
                   "errors": [str(e)[:300]]}
        ms = int((time.time() - t0) * 1000)
        area = rep.get("area") or {}
        row = {"name": name, "kind": item.get("kind"),
               "ok": bool(rep.get("ok")), "source": rep.get("source"),
               "cells": area.get("cells"), "ffs": area.get("ffs"),
               "fmax": area.get("fmax_mhz"),
               "timing_met": area.get("timing_met"),
               "ms": ms, "model": rep.get("model"),
               "repairs": rep.get("repairs"),
               "error": None if rep.get("ok") else
               ((rep.get("errors") or [""])[0][:200])}
        _record(row)
        rows.append(row)
        log(f"[{i:2d}/{len(corpus)}] {name:18s} "
            f"{'PASS' if row['ok'] else 'FAIL':4s} "
            f"cells={row['cells']} ffs={row['ffs']} "
            f"fmax={row['fmax']} "
            f"src={row['source']} {ms/1000:.1f}s")
        # free the big model between chips so RAM stays healthy
        if str(row.get("source") or "").startswith("model"):
            try:
                M.unload()
                time.sleep(3)
            except Exception:
                pass
    total = time.time() - t_start
    summary = _summary(rows, corpus, total)
    log("\n" + summary["text"])
    return summary


def status() -> dict:
    """Summarise results so far (reads results.jsonl)."""
    return _summary([], [], 0.0)


def _summary(rows, corpus, seconds):
    all_rows = []
    try:
        with open(RESULTS, encoding="utf-8") as f:
            for ln in f:
                try:
                    all_rows.append(json.loads(ln))
                except Exception:
                    pass
    except Exception:
        pass
    latest = {}
    for r in all_rows:
        latest[r["name"]] = r
    vals = list(latest.values())
    passed = [r for r in vals if r.get("ok")]
    by_src = {}
    for r in passed:
        by_src[r.get("source")] = by_src.get(r.get("source"), 0) + 1
    cells = sum((r.get("cells") or 0) for r in passed)
    ffs = sum((r.get("ffs") or 0) for r in passed)
    timed = [r for r in passed if r.get("fmax") is not None]
    met = sum(1 for r in timed if r.get("timing_met"))
    slowest = min(timed, key=lambda r: r["fmax"]) if timed else None
    lines = ["# ROX N — batch chip build", "",
             f"- designs attempted : {len(vals)}",
             f"- passed            : {len(passed)}",
             f"- failed            : {len(vals) - len(passed)}",
             f"- by source         : {by_src}",
             f"- total area        : {cells} cells / {ffs} FFs",
             f"- clocked designs   : {len(timed)} (timing met {met})",
             (f"- worst Fmax        : {slowest['fmax']:.1f} MHz "
              f"({slowest['name']})") if slowest else
             "- worst Fmax        : n/a (no clocked designs)",
             f"- wall time         : {seconds/60:.1f} min", "",
             "| chip | result | source | cells | FFs | Fmax | time |",
             "|---|---|---|---|---|---|---|"]
    for r in sorted(vals, key=lambda x: x["name"]):
        fm = (f"{r['fmax']:.0f} MHz" if r.get("fmax") is not None else "-")
        lines.append(f"| {r['name']} | {'PASS' if r.get('ok') else 'FAIL'} "
                     f"| {r.get('source') or '-'} | {r.get('cells') or '-'} "
                     f"| {r.get('ffs') or '-'} | {fm} "
                     f"| {(r.get('ms') or 0)/1000:.1f}s |")
    text = "\n".join(lines)
    try:
        with open(os.path.join(OUT, "BATCH_REPORT.md"), "w",
                  encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    return {"attempted": len(vals), "passed": len(passed),
            "failed": len(vals) - len(passed), "by_source": by_src,
            "cells": cells, "ffs": ffs, "seconds": round(seconds, 1),
            "clocked": len(timed), "timing_met": met,
            "worst_fmax": (slowest["fmax"] if slowest else None),
            "text": text, "outdir": OUT}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--novel-only", action="store_true")
    a = ap.parse_args()
    corpus = default_corpus()
    if a.novel_only:
        corpus = [c for c in corpus if not c.get("kind")]
    run_batch(corpus=corpus, limit=a.limit, resume=not a.no_resume)
