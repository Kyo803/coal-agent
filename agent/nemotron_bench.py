"""Benchmark Nemotron (Nebius Token Factory) on the designs the local 7B failed.

This is the script that produces the numbers the hackathon form asks for:

  * which model, and why that size
  * how good its output was (pass rate, not vibes)
  * how it compares to the models we used before
  * what Nebius/Token Factory actually did for the workflow

    $env:NEBIUS_API_KEY = "..."
    py -3.15 nemotron_bench.py                 # default Nemotron-3 Super 120B
    py -3.15 nemotron_bench.py --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
    py -3.15 nemotron_bench.py --model nvidia/Nemotron-3-Ultra-550b-a55b
    py -3.15 nemotron_bench.py --list          # show available model ids
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from chipflow import model as M          # noqa: E402
from chipflow import unique as U         # noqa: E402

MAIN = os.path.join(os.path.expanduser("~"), ".coal", "work", "chips",
                    "_unique", "results.jsonl")
BENCH = os.path.join(os.path.expanduser("~"), ".coal", "work", "nemotron_bench")


def _load(path):
    rows = {}
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                rows[r["name"]] = r
    except Exception:
        pass
    return rows


def main():
    args = sys.argv[1:]
    if "--list" in args:
        if not M._key():
            print("set NEBIUS_API_KEY first")
            return 1
        for mid in M.list_models():
            print(mid)
        return 0

    model = M.NEBIUS_MODEL
    if "--model" in args:
        model = args[args.index("--model") + 1]
    limit = 99
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    if not M._key():
        print("NEBIUS_API_KEY is not set - cannot benchmark the hosted model.\n"
              "  $env:NEBIUS_API_KEY = \"...\"")
        return 1

    baseline = _load(MAIN)
    targets = [n for n, r in baseline.items() if not r.get("ok")]
    specs = [s for s in U.SPECS if s[0] in targets][:limit]
    if not specs:
        print("nothing to benchmark (no failing designs in the catalogue)")
        return 0

    print(f"benchmarking {len(specs)} failing designs with {model}")
    U.OUT = BENCH
    U.RESULTS = os.path.join(BENCH, "results.jsonl")
    U.REPORT = os.path.join(BENCH, "NEMOTRON_BENCH.md")
    U.SPECS = specs          # <- run() reads the module-level SPECS
    os.makedirs(BENCH, exist_ok=True)
    # start clean so an earlier partial run cannot mix into this one
    for stale in (U.RESULTS, U.REPORT):
        if os.path.exists(stale):
            os.remove(stale)

    U.run(limit=len(specs), model=model, repairs=1, det_only=False)

    got = _load(U.RESULTS)
    rows = []
    for name, cat, spec, use in specs:
        b = baseline.get(name, {})
        n = got.get(name, {})
        rows.append({
            "name": name, "cat": cat,
            "local": "PASS" if b.get("ok") else "FAIL",
            "nemotron": ("PASS" if n.get("ok") else
                         "FAIL" if n else "not run"),
            "cells": n.get("cells"), "ffs": n.get("ffs"),
            "fmax": n.get("fmax"), "ms": n.get("ms"),
            "why": (n.get("error") or "")[:90],
        })

    n_pass = sum(1 for r in rows if r["nemotron"] == "PASS")
    l_pass = sum(1 for r in rows if r["local"] == "PASS")
    lines = [
        "# Nemotron benchmark - the designs the local 7B could not build", "",
        f"- model           : `{model}`",
        f"- endpoint        : `{M.NEBIUS_URL}`",
        f"- designs         : {len(rows)}",
        f"- local 7B        : {l_pass}/{len(rows)} passed",
        f"- Nemotron        : {n_pass}/{len(rows)} passed",
        "", "| design | category | local 7B | Nemotron | cells/FF | Fmax |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['name']}` | {r['cat']} | {r['local']} | {r['nemotron']} "
            f"| {r.get('cells') or '-'}/{r.get('ffs') or '-'} "
            f"| {r.get('fmax') or '-'} |")
    lines += [
        "", "## Answers to the submission questions", "",
        f"**Model used:** `{model}`.",
        "",
        f"**Measured output quality:** {n_pass}/{len(rows)} of the designs the "
        f"7B failed were built and passed the full gate "
        f"(lint + simulation + synthesis + formal + place & route), versus "
        f"{l_pass}/{len(rows)} locally.",
        "",
        "**How it was used:** out of the box - no fine-tuning. It is prompted "
        "to emit either a block graph or RTL, and its output is only accepted "
        "if an independently written Python reference model agrees with it "
        "cycle by cycle.",
        "",
        "**Where Token Factory helped:** the design step is the only part that "
        "needs a large model. Hosted inference removed the 9 GB local RAM "
        "ceiling and the ~20 tok/s CPU bottleneck, so the whole design step "
        "runs on GPU while verification stays local and deterministic.",
    ]
    text = "\n".join(lines)
    with open(U.REPORT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
