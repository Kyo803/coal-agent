"""Chip-design tool handlers: RTL planning/review/verification using the
chip architect (chip-design-ai-v4, a local 3B model) + deterministic checks.
"""
from __future__ import annotations

import os
import re

from chip_architect import ChipArchitect
from .handlers_fs import _resolve


def _arch():
    return ChipArchitect()


def chip_plan(args, ctx):
    """Ask the chip architect to plan a module's port list."""
    desc = args.get("description", "")
    if not desc:
        return {"ok": False, "output": "description required"}
    try:
        a = _arch()
        res = a.plan_ports(desc)
        ports = "\n".join(a.port_line(p) for p in res["ports"])
        return {"ok": True,
                "output": f"planned ports:\n{ports}\n\nheader:\n"
                          f"{res['text'][:1200]}"}
    except Exception as e:
        return {"ok": False, "output": f"chip_plan failed: {e}"}


def chip_review(args, ctx):
    """Have the chip architect check RTL ports against a contract."""
    a = _arch()
    rtl = args.get("rtl") or ""
    path = args.get("path")
    if not rtl and path:
        try:
            rtl = open(_resolve(path, ctx), encoding="utf-8",
                       errors="ignore").read()
        except Exception as e:
            return {"ok": False, "output": f"read failed: {e}"}
    contract = args.get("contract") or ""
    if not contract:
        return {"ok": False, "output": "contract required"}
    try:
        out = a.review(rtl, contract)
        return {"ok": True, "output": out[:1800]}
    except Exception as e:
        return {"ok": False, "output": f"chip_review failed: {e}"}


def chip_build(args, ctx):
    """Build a verified chip block through the full gate.

    Deterministic for known blocks (counter/alu/shiftreg/fsm/pwm/uart);
    otherwise a local model writes it and gate errors are fed back for
    bounded repair rounds. 'ok' means lint + synth + formal passed
    (+ equivalence when a golden exists).
    """
    try:
        import chipflow
    except Exception as e:
        return {"ok": False, "output": f"chipflow unavailable: {e}"}
    name = args.get("name") or "chip"
    spec = args.get("spec") or args.get("description") or ""
    kind = args.get("kind")
    params = args.get("params") or {}
    if isinstance(params, str):
        import json as _json
        try:
            params = _json.loads(params)
        except Exception:
            params = {}
    if not spec and not kind:
        return {"ok": False, "output": "spec or kind required"}
    rep = chipflow.build(name, spec=spec, kind=kind, params=params,
                         max_repairs=int(args.get("repairs") or 3))
    lines = [chipflow.summary_text(rep),
             f"  source: {rep.get('source')}"]
    if rep.get("repairs"):
        lines.append(f"  repairs: {rep['repairs']}")
    if rep.get("path"):
        lines.append(f"  report: {rep['path']}")
    for k, v in (rep.get("views") or {}).items():
        if isinstance(v, str):
            lines.append(f"  {k:10s}: {v}")
    return {"ok": bool(rep.get("ok")), "output": "\n".join(lines)}


def chip_views(args, ctx):
    """(Re)generate the 2D/3D views for an existing verified design."""
    try:
        import json as _json

        import chipflow
        from chipflow import views as V
    except Exception as e:
        return {"ok": False, "output": f"chipflow unavailable: {e}"}
    p = args.get("path")
    if not p:
        return {"ok": False, "output": "path required"}
    d = _resolve(p, ctx)
    if not os.path.isdir(d):
        return {"ok": False, "output": f"not a directory: {d}"}
    top = args.get("top")
    stats = {}
    for f in os.listdir(d):
        if f.endswith("-report.json"):
            try:
                rep = _json.load(open(os.path.join(d, f), encoding="utf-8"))
            except Exception:
                continue
            top = top or rep.get("design")
            area = rep.get("area") or {}
            stats = {"cells": area.get("cells") or 0,
                     "ffs": area.get("ffs") or 0,
                     "cell_types": rep.get("cell_types") or {}}
            break
    if not top:
        return {"ok": False, "output": "top module unknown"}
    res = V.make_all(d, top, stats, formats=("glb", "fbx", "png"))
    lines = [f"views for {top}:"]
    ok = True
    for k, v in res.items():
        if isinstance(v, str) and os.path.exists(v):
            lines.append(f"  {k:10s}: {v}")
        else:
            ok = False
            lines.append(f"  {k:10s}: {v}")
    return {"ok": ok, "output": "\n".join(lines)}


def chip_gate(args, ctx):
    """Run the full gate on an existing directory of Verilog."""
    try:
        import chipflow
    except Exception as e:
        return {"ok": False, "output": f"chipflow unavailable: {e}"}
    p = args.get("path")
    if not p:
        return {"ok": False, "output": "path required"}
    d = _resolve(p, ctx)
    if not os.path.isdir(d):
        return {"ok": False, "output": f"not a directory: {d}"}
    top = args.get("top")
    if not top:
        for f in os.listdir(d):
            if f.endswith(".v") and not f.startswith("tb_"):
                try:
                    txt = open(os.path.join(d, f), encoding="utf-8",
                               errors="ignore").read()
                except Exception:
                    continue
                m = re.search(r"\bmodule\s+([A-Za-z_]\w*)", txt)
                if m:
                    top = m.group(1)
                    break
    if not top:
        return {"ok": False, "output": "could not determine top module"}
    rep = chipflow.verify_dir(d, top, tb=args.get("tb"),
                              gold_rtl=args.get("gold"))
    return {"ok": bool(rep.get("ok")),
            "output": chipflow.summary_text(rep)}


def chip_tools(args, ctx):
    """Report the HDL toolchain and the RAM-aware model choice."""
    try:
        import chipflow
        from chipflow import compositions, pnr
        from chipflow import core
        from chipflow import model as M
        from chipflow.designs import GENERATORS
        avail = core.available()
        ym = M.pick_model()
        installed = M.installed()
        free = round(M.free_ram_gb(), 1)
        pnr_ok = pnr.available()
    except Exception as e:
        return {"ok": False, "output": f"chipflow unavailable: {e}"}
    lines = ["chip toolchain:"]
    for k, v in avail.items():
        lines.append(f"  {k:18s} {v}")
    lines.append(f"  place & route      {pnr_ok} (iCE40 HX8K, Fmax)")
    lines.append(f"  free RAM           {free} GB")
    lines.append(f"  RTL model          {ym or 'none (deterministic only)'}")
    lines.append(f"  installed models   {installed}")
    lines.append(f"  blocks             {sorted(set(GENERATORS))}")
    lines.append(f"  compositions       {compositions.names()}")
    return {"ok": True, "output": "\n".join(lines)}


def chip_batch(args, ctx):
    """Run / check / stop a batch of chip builds (ROX N designs a corpus)."""
    try:
        from chipflow import batch as BT
    except Exception as e:
        return {"ok": False, "output": f"chipflow unavailable: {e}"}
    action = (args.get("action") or "run").lower()
    if action == "stop":
        os.makedirs(BT.OUT, exist_ok=True)
        with open(BT.STOP, "w", encoding="utf-8") as f:
            f.write("1")
        return {"ok": True, "output": "batch stop requested"}
    if action == "status":
        try:
            s = BT.status()
        except Exception as e:
            return {"ok": False, "output": f"status failed: {e}"}
        return {"ok": True, "output": s["text"]}
    # run: launch detached so it survives the tool call
    import subprocess
    import sys
    limit = int(args.get("limit") or 50)
    os.makedirs(BT.OUT, exist_ok=True)
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logf = open(os.path.join(BT.OUT, "run.log"), "a", encoding="utf-8")
    errf = open(os.path.join(BT.OUT, "run.err"), "a", encoding="utf-8")
    p = subprocess.Popen([exe, "-m", "chipflow.batch", "--limit", str(limit)],
                         cwd=root, stdout=logf, stderr=errf,
                         creationflags=0x08000000)
    return {"ok": True, "output":
            f"batch started (pid {p.pid}, limit {limit}).\n"
            f"  results: {os.path.join(BT.OUT, 'results.jsonl')}\n"
            f"  report : {os.path.join(BT.OUT, 'BATCH_REPORT.md')}\n"
            f"  check  : chip_batch action=status"}


def chip_unique(args, ctx):
    """Run / check / stop the 50-unique-chip design run."""
    try:
        from chipflow import unique as U
    except Exception as e:
        return {"ok": False, "output": f"chipflow unavailable: {e}"}
    action = (args.get("action") or "run").lower()
    if action == "stop":
        os.makedirs(U.OUT, exist_ok=True)
        with open(U.STOP, "w", encoding="utf-8") as f:
            f.write("1")
        return {"ok": True, "output": "unique-chip run stop requested"}
    if action == "status":
        try:
            s = U.summarize()
        except Exception as e:
            return {"ok": False, "output": f"status failed: {e}"}
        return {"ok": True,
                "output": s["text"].split("## Per-chip detail")[0]}
    import subprocess
    import sys
    limit = int(args.get("limit") or 50)
    model = str(args.get("model") or "14b")
    os.makedirs(U.OUT, exist_ok=True)
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logf = open(os.path.join(U.OUT, "run.log"), "a", encoding="utf-8")
    errf = open(os.path.join(U.OUT, "run.err"), "a", encoding="utf-8")
    p = subprocess.Popen(
        [exe, "-m", "chipflow.unique", "--limit", str(limit),
         "--model", model],
        cwd=root, stdout=logf, stderr=errf, creationflags=0x08000000)
    return {"ok": True, "output":
            f"unique-chip run started (pid {p.pid}, limit {limit}, "
            f"model {model})\n  report: {U.REPORT}"}


def chip_verify(args, ctx):
    """Deterministic check: does a module's ports match expected?
    expected: comma/newline list, e.g. 'input a, input b, output y'
    (or plain names to just check existence)."""
    a = _arch()
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    try:
        rtl = open(_resolve(path, ctx), encoding="utf-8",
                   errors="ignore").read()
    except Exception as e:
        return {"ok": False, "output": f"read failed: {e}"}
    expected = args.get("expected") or ""
    ports = []
    for tok in re.split(r"[,\n]+", expected):
        tok = tok.strip()
        m = re.match(r"\s*(input|output|inout)\s+(.+)", tok, re.I)
        if m:
            ports.append({"name": m.group(2).strip(),
                          "dir": m.group(1).lower()})
    if not ports:
        got = {p["name"] for p in a.extract_ports(rtl)}
        missing = [n.strip() for n in re.split(r"[,\n]+", expected)
                   if n.strip() and n.strip() not in got]
        ok = not missing
        extra = []
    else:
        ok, missing, extra = a.verify_contract(rtl, ports)
    return {"ok": True,
            "output": f"chip_verify: {'OK' if ok else 'MISMATCH'}\n"
                      f"missing: {missing}\nextra: {extra}"}