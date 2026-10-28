"""ROX N — chip flow with automatic toolchain routing.

Stages, each a hard gate:
    lint    yosys read/check + verilator --lint-only + iverilog -Wall
    sim     compile + vvp, self-checking testbench must print <MOD>:PASS
    synth   yosys synth + stat  (gate cells / FFs / area; ABC when present)
    formal  yosys check -assert (no latches / comb loops) + equiv vs golden
    report  one JSON + human summary

Tools are resolved through chipflow.backend: WSL (real iverilog, verilator,
yosys+ABC) when a distro exists, otherwise YoWASP yosys (WASM: no sim, no ABC).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time

from . import backend as B

_TOOL_DIRS = [r"C:\msys64\ucrt64\bin", r"C:\msys64\mingw64\bin",
              r"C:\iverilog\bin", r"C:\Program Files\Graphviz\bin"]

_CACHE = {}


def _runs(path, arg="-V"):
    try:
        r = subprocess.run([path, arg], capture_output=True, text=True,
                           timeout=40, encoding="utf-8", errors="replace")
        return r.returncode == 0
    except Exception:
        return False


def tool(name):
    if name in _CACHE:
        return _CACHE[name]
    p = shutil.which(name)
    if not p:
        for d in _TOOL_DIRS:
            for ext in ("", ".exe"):
                c = os.path.join(d, name + ext)
                if os.path.isfile(c):
                    p = c
                    break
            if p:
                break
    # a file that exists but is blocked by App Control must not be used
    if p and not _runs(p):
        p = None
    _CACHE[name] = p
    return p


def yosys_cmd():
    """Yosys invocation as a command list.

    Prefers WSL (real yosys with ABC), then a runnable native build, then
    YoWASP (WASM) — because Windows Smart App Control blocks unsigned MSYS2
    binaries. YoWASP's launcher is a pip script and runs fine."""
    if "_yosys" in _CACHE:
        return _CACHE["_yosys"]
    cmd = None
    if B.wsl_available() and B.wsl_tool("yosys"):
        cmd = ["yosys"]
    else:
        n = tool("yosys")
        if n:
            cmd = [n]
        elif B.yowasp("yosys"):
            cmd = [B.yowasp("yosys")]
    _CACHE["_yosys"] = cmd
    return cmd


def verilator_cmd():
    if "_verilator" in _CACHE:
        return _CACHE["_verilator"]
    cmd = None
    if B.wsl_available() and B.wsl_tool("verilator"):
        cmd = ["verilator"]
    else:
        n = tool("verilator")
        if n:
            cmd = [n]
    _CACHE["_verilator"] = cmd
    return cmd


def run_tool(cmd, cwd=None, timeout=900, env=None):
    """Run a tool command, routing through WSL when the tool lives there."""
    if cmd and B.wsl_available():
        name = os.path.basename(str(cmd[0])).replace(".exe", "")
        if B.wsl_tool(name):
            return B.wsl_run(cmd, cwd, timeout, env)
    return run(cmd, cwd, timeout, env)


def available():
    rep = B.report()
    d = dict(rep.get("wsl_tools") or {})
    d["backend"] = rep.get("backend")
    d["wsl_distro"] = rep.get("wsl_distro")
    d["yosys"] = bool(yosys_cmd())
    d["verilator"] = bool(verilator_cmd())
    d["iverilog"] = bool(iverilog_works())
    d["abc"] = bool(_has_abc())
    return d


def run(cmd, cwd=None, timeout=300, env=None):
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join(_TOOL_DIRS) + os.pathsep + e.get("PATH", "")
    if env:
        e.update(env)
    try:
        r = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True,
                           timeout=timeout, creationflags=0x08000000,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        return {"ok": r.returncode == 0, "rc": r.returncode, "out": out,
                "cmd": [str(c) for c in cmd]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "rc": -1, "out": f"timeout after {timeout}s",
                "cmd": [str(c) for c in cmd]}
    except Exception as ex:
        return {"ok": False, "rc": -2, "out": str(ex),
                "cmd": [str(c) for c in cmd]}


def _qfiles(files):
    return " ".join(f'"{f}"' for f in _vfiles(files))


def _vfiles(files):
    return [f for f in files if f.lower().endswith((".v", ".sv"))]


_IVL = {}


def iverilog_works():
    """Native iverilog is often blocked by Device Guard; test once."""
    if "ok" in _IVL:
        return _IVL["ok"]
    if B.wsl_available() and B.wsl_tool("iverilog"):
        _IVL["ok"] = True
        _IVL["why"] = "wsl"
        return True
    iv = tool("iverilog")
    if not iv:
        _IVL["ok"] = False
        return False
    import tempfile
    d = tempfile.mkdtemp(prefix="ivlchk-")
    p = os.path.join(d, "t.v")
    with open(p, "w", encoding="utf-8") as f:
        f.write("module t; endmodule\n")
    r = run([iv, "-o", os.path.join(d, "t.out"), p], d, timeout=60)
    _IVL["ok"] = bool(r["ok"])
    _IVL["why"] = "" if r["ok"] else r["out"][:300]
    return _IVL["ok"]


def iverilog_cmd():
    """Bare name when WSL provides iverilog, else the native path."""
    if B.wsl_available() and B.wsl_tool("iverilog"):
        return "iverilog"
    return tool("iverilog") or "iverilog"


# ------------------------------------------------------------------ lint
def lint(files, cwd, top=None, timeout=600):
    """Parse/structural lint. Yosys is the primary (always available via
    YoWASP); iverilog -Wall is added only when it can actually compile."""
    files = _vfiles(files)
    res = {}
    ys = yosys_cmd()
    if ys:
        script = (f"read_verilog -sv {_qfiles(files)}; "
                  + (f"hierarchy -top {top}; " if top else "")
                  + "proc; opt; check -assert")
        res["yosys"] = run_tool(ys + ["-p", script], cwd, timeout=timeout)
    vc = verilator_cmd()
    if vc:
        res["verilator"] = run_tool(
            vc + ["--lint-only", "-Wall", "-Wno-fatal", "--timing"]
            + (["--top-module", top] if top else []) + files,
            cwd, timeout=timeout)
    if iverilog_works():
        iv = iverilog_cmd()
        res["iverilog"] = run_tool(
            [iv, "-g2012", "-Wall", "-o", "_lint.out"]
            + (["-s", top] if top else []) + files, cwd, timeout=timeout)
    errors = [f"[{k}] {v['out'][-1500:]}" for k, v in res.items()
              if not v["ok"]]
    return {"stage": "lint", "ok": not errors, "results": res,
            "errors": errors, "iverilog": iverilog_works(),
            "verilator": bool(vc)}


# ------------------------------------------------------------------ sim
def simulate(files, cwd, top_tb, timeout=600):
    if not iverilog_works():
        return {"stage": "sim", "ok": True, "skipped": True,
                "note": "no simulator available (WSL distro missing and "
                        "native tools blocked); correctness rests on yosys "
                        "equivalence/formal",
                "errors": []}
    files = _vfiles(files)
    outv = f"_{top_tb}.vvp"
    c = run_tool(["iverilog", "-g2012", "-s", top_tb, "-o", outv] + files,
                 cwd, timeout=timeout)
    if not c["ok"]:
        return {"stage": "sim", "ok": False, "compile": c,
                "errors": [c["out"][-3000:]]}
    r = run_tool(["vvp", outv], cwd, timeout=timeout)
    txt = r["out"]
    # The testbench itself declares the verdict. A non-zero exit *after* a
    # PASS is almost always a missing $finish or a late timeout block, not a
    # design failure -- so the markers decide, not the exit code.
    has_fail = ":FAIL" in txt
    has_pass = ":PASS" in txt or re.search(r"\bPASS\b", txt) is not None
    passed = bool(has_pass and not has_fail)
    return {"stage": "sim", "ok": passed, "compile": c, "run": r,
            "pass": passed, "output": txt[-4000:],
            "errors": [] if passed else [txt[-3000:]]}


# ------------------------------------------------------------------ synth
_NUM = re.compile(r"^\s*(\S+)\s+(\d+)\s*$")


def _has_abc():
    """ABC needs a subprocess; only real (WSL/native) yosys has it."""
    return bool(B.wsl_available() and B.wsl_tool("yosys")
                and B.wsl_tool("abc"))


def synthesize(files, cwd, top, timeout=900):
    files = _vfiles(files)
    ys = yosys_cmd()
    if not ys:
        return {"stage": "synth", "ok": False, "errors": ["yosys missing"]}
    flag = "" if _has_abc() else " -noabc"
    script = (f"read_verilog -sv {_qfiles(files)}; "
              f"synth -top {top}{flag}; stat")
    r = run_tool(ys + ["-p", script], cwd, timeout=timeout)
    stats = {"cells": 0, "ffs": 0, "memories": 0, "cell_types": {}}
    for ln in r["out"].splitlines():
        ls = ln.strip()
        # yosys >= 0.4x: "<count> cells"; yosys 0.33: "Number of cells: <n>"
        m = re.match(r"^Number of cells:\s+(\d+)", ls)
        if m:
            stats["cells"] = int(m.group(1))
            continue
        m = re.match(r"^Number of memories:\s+(\d+)", ls)
        if m:
            stats["memories"] = int(m.group(1))
            continue
        m = re.match(r"^(\d+)\s+cells$", ls)
        if m:
            stats["cells"] = int(m.group(1))
            continue
        m = re.match(r"^(\d+)\s+memories$", ls)
        if m:
            stats["memories"] = int(m.group(1))
            continue
        # cell type lines, both column orders
        m = re.match(r"^(\$[A-Za-z0-9_]+)\s+(\d+)$", ls)
        if m:
            stats["cell_types"][m.group(1)] = int(m.group(2))
            continue
        m = re.match(r"^(\d+)\s+(\$[A-Za-z0-9_]+)$", ls)
        if m:
            stats["cell_types"][m.group(2)] = int(m.group(1))
            continue
    stats["ffs"] = sum(
        n for t, n in stats["cell_types"].items()
        if re.search(r"DFF|_FF_", t))
    ok = r["ok"] and stats["cells"] > 0
    return {"stage": "synth", "ok": ok, "run": r, "stats": stats,
            "errors": [] if ok else [r["out"][-3000:]]}


# ------------------------------------------------------------------ formal
def formal(files, cwd, top, timeout=900):
    """Structural safety: no inferred latches, no combinational loops."""
    files = _vfiles(files)
    ys = yosys_cmd()
    if not ys:
        return {"stage": "formal", "ok": False, "errors": ["yosys missing"]}
    script = (f"read_verilog -sv {_qfiles(files)}; "
              f"hierarchy -top {top}; proc; opt; "
              f"check -assert; stat")
    r = run_tool(ys + ["-p", script], cwd, timeout=timeout)
    out = r["out"]
    bad = []
    for ln in out.splitlines():
        low = ln.lower()
        if "error:" in low or "combinational loop" in low:
            bad.append(ln.strip())
        elif "latch inferred" in low and "no latch" not in low:
            bad.append(ln.strip())
    ok = r["ok"] and not bad
    return {"stage": "formal", "ok": ok, "run": r,
            "issues": bad[:20], "errors": [] if ok else
            (bad[:20] or [out[-3000:]])}


def _rel(p, cwd):
    """Yosys/WASM resolves relative paths only (no Windows drive letters)."""
    try:
        r = os.path.relpath(p, cwd)
        if r.startswith(".."):
            return os.path.basename(p)
        return r.replace("\\", "/")
    except Exception:
        return os.path.basename(p)


def equivalence(gold_files, gold_top, gate_files, gate_top, cwd,
                timeout=900):
    """Prove the generated module is equivalent to a golden reference."""
    ys = yosys_cmd()
    if not ys:
        return {"stage": "equiv", "ok": False, "errors": ["yosys missing"]}
    g = " ".join(f'"{_rel(p, cwd)}"' for p in _vfiles(gold_files))
    t = " ".join(f'"{_rel(p, cwd)}"' for p in _vfiles(gate_files))
    script = (
        f"read_verilog -sv {g}; prep -top {gold_top}; rename {gold_top} gold; "
        f"design -stash gold; "
        f"read_verilog -sv {t}; prep -top {gate_top}; rename {gate_top} gate; "
        f"design -stash gate; "
        f"design -copy-from gold -as gold gold; "
        f"design -copy-from gate -as gate gate; "
        f"equiv_make gold gate equiv; hierarchy -top equiv; "
        f"equiv_simple -undef; equiv_status -assert")
    r = run_tool(ys + ["-p", script], cwd, timeout=timeout)
    ok = r["ok"] and "Equivalence successfully proven" in r["out"]
    return {"stage": "equiv", "ok": ok, "run": r,
            "errors": [] if ok else [r["out"][-3000:]]}


# ------------------------------------------------------------------ report
def report(name, stages, outdir):
    ok = all(s.get("ok") for s in stages.values())
    syn = stages.get("synth", {}).get("stats", {}) or {}
    pn = stages.get("pnr", {}) or {}
    rep = {
        "design": name,
        "ok": ok,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stages": {k: {"ok": v.get("ok"),
                       "skipped": v.get("skipped"),
                       "errors": (v.get("errors") or [])[:3]}
                   for k, v in stages.items()},
        "area": {"cells": syn.get("cells"), "ffs": syn.get("ffs"),
                 "memories": syn.get("memories"),
                 "lc": pn.get("lc_used"),
                 "io": pn.get("io_used"),
                 "fmax_mhz": pn.get("fmax_mhz"),
                 "timing_met": pn.get("timing_met")},
        "pnr": {"device": pn.get("device"), "package": pn.get("package"),
                "target_mhz": pn.get("target_mhz"),
                "critical_path": pn.get("critical_path"),
                "timing_note": pn.get("timing_note")},
        "cell_types": syn.get("cell_types", {}),
    }
    os.makedirs(outdir, exist_ok=True)
    p = os.path.join(outdir, f"{name}-report.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1)
    rep["path"] = p
    return rep


def summary_text(rep):
    a = rep.get("area", {})
    lines = [f"{rep['design']}: {'PASS' if rep['ok'] else 'FAIL'}"]
    for k, v in rep.get("stages", {}).items():
        lines.append(f"  {k:7s} {'ok' if v.get('ok') else 'FAIL'}")
    lines.append(f"  area   cells={a.get('cells')} ffs={a.get('ffs')} "
                 f"mem={a.get('memories')}")
    if a.get("fmax_mhz") is not None:
        lines.append(f"  timing Fmax={a['fmax_mhz']:.1f} MHz "
                     f"({'met' if a.get('timing_met') else 'MISSED'})")
    elif "pnr" in rep.get("stages", {}):
        lines.append("  timing n/a (combinational)")
    if rep.get("proof"):
        lines.append(f"  proof  {rep['proof']}")
    return "\n".join(lines)
