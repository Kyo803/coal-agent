"""Fair Nemotron RTL-quality benchmark: model writes RTL, we supply the TB.

The first benchmark (nemotron_bench.py) measured the weak path: the model
writes BOTH the RTL and the testbench. 4 of its 6 failures were the testbench
failing to compile, which says nothing about the RTL.

This isolates RTL quality the way the project is actually designed to work:

  * the model is given the specification and the exact port list
  * it writes only the Verilog
  * the testbench comes from the block's INDEPENDENT Python reference model
  * the full gate decides pass/fail

Run:
    $env:NEBIUS_API_KEY = "..."
    py -3.15 nemotron_rtl_bench.py
    py -3.15 nemotron_rtl_bench.py --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from chipflow import designs, flow, model as M, unique as U   # noqa: E402

OUT = os.path.join(os.path.expanduser("~"), ".coal", "work", "nemotron_rtl")
REPORT = os.path.join(OUT, "NEMOTRON_RTL.md")

# catalogue names that map to a reference-model block
DESIGNS = ["parity", "popcount", "bitrev", "edge_detect", "lfsr8",
           "prio16", "satadd", "hamming_enc", "seqdet", "barrelshift"]


def main() -> int:
    args = sys.argv[1:]
    model = M.NEBIUS_MODEL
    if "--model" in args:
        model = args[args.index("--model") + 1]
    repairs = 0
    if "--repairs" in args:
        repairs = int(args[args.index("--repairs") + 1])
    if not M._key():
        print("NEBIUS_API_KEY is not set")
        return 1

    specs = {s[0]: s for s in U.SPECS}
    os.makedirs(OUT, exist_ok=True)
    rows = []

    for name in DESIGNS:
        kind = U.DETERMINISTIC[name][0]
        ref = designs.generate_block(kind)
        top = ref["top"]
        ports_txt = U._ports_text(ref["rtl"], top)
        cat, spec = specs[name][1], specs[name][2]

        t0 = time.time()
        gen = M.generate_rtl(spec, top, ports=[ports_txt], model=model)
        dt = round(time.time() - t0, 1)

        if not gen.get("ok"):
            rows.append({"name": name, "ok": False, "why": "generation: "
                         + str(gen.get("reason"))[:60], "secs": dt})
            print(f"  {name:12s} FAIL (generation) {dt}s")
            continue

        rtl = M._normalise(gen["rtl"], top)
        # the independent reference-model testbench, NOT model-written
        rep = flow.build_design(name, rtl, ref["tb"], top=top)
        rounds = 0
        while not rep.get("ok") and rounds < repairs:
            rounds += 1
            fx = M.repair_rtl(rtl, top, U._error_for_repair(rep),
                              model=model, tb=ref["tb"])
            if not fx.get("ok") or not fx.get("rtl"):
                break
            rtl = M._normalise(fx["rtl"], top)
            rep = flow.build_design(name, rtl, ref["tb"], top=top)
        ok = bool(rep.get("ok"))
        bad = [k for k, v in (rep.get("stages") or {}).items()
               if not (v.get("ok") if isinstance(v, dict) else bool(v))]
        why = ""
        if not ok:
            for k in bad:
                v = (rep.get("stages") or {}).get(k)
                if isinstance(v, dict) and v.get("errors"):
                    why = f"{k}: {str(v['errors'][0]).strip()[:100]}"
                    break
        # keep the markdown table on one line
        why = " ".join(why.split())
        pnr = (rep.get("stages") or {}).get("pnr") or {}
        rows.append({"name": name, "ok": ok, "why": why, "secs": dt,
                     "rounds": rounds,
                     "cells": pnr.get("cells"), "ffs": pnr.get("ffs"),
                     "fmax": pnr.get("fmax")})
        print(f"  {name:12s} {'PASS' if ok else 'FAIL'} {dt}s "
              f"repairs={rounds} {why[:60]}")

    npass = sum(1 for r in rows if r["ok"])
    total = len(rows)
    lines = [
        "# Nemotron RTL-only benchmark (independent reference-model TB)", "",
        f"- model    : `{model}`",
        f"- endpoint : `{M.NEBIUS_URL}`",
        f"- method   : model writes RTL from spec + exact ports; the testbench",
        "             comes from the block's independent Python reference model",
        f"- repairs  : {repairs} (model sees the gate's error text and retries)",
        f"- result   : **{npass}/{total} passed the full gate**", "",
        "| design | result | time | repairs | cells/FF | Fmax | failure |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['name']}` | {'PASS' if r['ok'] else 'FAIL'} | {r['secs']}s "
            f"| {r.get('rounds', 0)} "
            f"| {r.get('cells') or '-'}/{r.get('ffs') or '-'} "
            f"| {r.get('fmax') or '-'} | {r.get('why') or '-'} |")
    lines += [
        "", "## What this means", "",
        f"Nemotron's RTL passed **{npass}/{total}** when checked against an "
        "independent reference model. The failures are real RTL bugs, not "
        "testbench artefacts -- the testbench was never written by the model.",
        "",
        "This is the number to compare against other models: same spec, same "
        "ports, same reference-model testbench, same gate.",
    ]
    text = "\n".join(lines)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
