"""Place-and-route + static timing on iCE40 via nextpnr.

Synthesis tells you a chip *can* be built; place-and-route tells you whether
it actually fits and how fast it runs. This stage runs the real flow inside
WSL (yosys `synth_ice40` -> `nextpnr-ice40`) and reports:

    lc / io        -> resources actually used
    fmax_mhz       -> achieved clock frequency
    timing_met     -> achieved >= target
    critical_path  -> the slowest register-to-register path

Combinational designs (no clock) are still placed and routed; their timing is
reported as unavailable rather than failed.

Device/package/frequency are configurable:
    COAL_FPGA_DEVICE=hx8k|up5k|lp384   (default hx8k)
    COAL_FPGA_PACKAGE=ct256            (default ct256)
    COAL_PNR_FREQ=24                   (target MHz, default 24)
    COAL_NO_PNR=1                      (disable the stage entirely)
"""
from __future__ import annotations

import json
import os
import re

from . import backend as B
from . import core

DEVICE = os.environ.get("COAL_FPGA_DEVICE", "hx8k")
PACKAGE = os.environ.get("COAL_FPGA_PACKAGE", "ct256")
TARGET_MHZ = float(os.environ.get("COAL_PNR_FREQ", "24"))

_FLAGS = {"hx8k": "--hx8k", "up5k": "--up5k", "lp384": "--lp384"}


def enabled() -> bool:
    if os.environ.get("COAL_NO_PNR", "").lower() in ("1", "true", "yes"):
        return False
    return available()


def available() -> bool:
    """nextpnr-ice40 + yosys must both exist inside WSL."""
    try:
        return bool(B.wsl_available() and B.wsl_tool("nextpnr-ice40")
                    and B.wsl_tool("yosys"))
    except Exception:
        return False


def _device_flag(device: str | None) -> str:
    return _FLAGS.get((device or DEVICE).lower(), "--hx8k")


def _sum_delay(path) -> float:
    total = 0.0
    for seg in path or []:
        try:
            total += float(seg.get("delay") or 0.0)
        except (TypeError, ValueError):
            pass
    return total


def _pick_critical(rep: dict):
    """Prefer a register-to-register path; else the slowest one available."""
    paths = rep.get("critical_paths") or []
    clocked = [p for p in paths
               if "posedge" in str(p.get("from", ""))
               and "posedge" in str(p.get("to", ""))]
    pool = clocked or paths
    if not pool:
        return None
    best = max(pool, key=lambda p: _sum_delay(p.get("path")))
    return {
        "from": best.get("from"),
        "to": best.get("to"),
        "delay_ns": round(_sum_delay(best.get("path")), 3),
    }


def place_and_route(files, cwd, top: str, freq_mhz: float | None = None,
                    device: str | None = None, package: str | None = None,
                    timeout: int = 900) -> dict:
    """Synthesise for iCE40, place, route, and report timing."""
    if not enabled():
        return {"stage": "pnr", "ok": True, "skipped": True,
                "note": "nextpnr-ice40 unavailable (or COAL_NO_PNR set)",
                "errors": []}

    files = core._vfiles(files)
    # WSL/nextpnr take paths relative to cwd; absolute Windows paths lose
    # their backslashes when the command is joined into a shell string.
    files = [os.path.relpath(f, cwd) if os.path.isabs(f) else f
             for f in files]
    # synthesis never wants the testbench (initial/@ blocks are not RTL)
    files = [f for f in files
             if not os.path.basename(f).startswith("tb_")]
    ys = core.yosys_cmd()
    if not ys:
        return {"stage": "pnr", "ok": False, "errors": ["yosys missing"]}

    freq = float(freq_mhz or TARGET_MHZ)
    netlist = f"_{top}_ice40.json"
    repf = f"_{top}_pnr.json"

    script = (f"read_verilog -sv {core._qfiles(files)}; "
              f"synth_ice40 -top {top} -json {netlist}")
    syn = core.run_tool(ys + ["-p", script], cwd, timeout=timeout)
    if not syn["ok"]:
        return {"stage": "pnr", "ok": False, "phase": "synth_ice40",
                "run": syn, "errors": [syn["out"][-2500:]]}

    cmd = ["nextpnr-ice40", _device_flag(device),
           "--package", package or PACKAGE,
           "--json", netlist,
           "--freq", f"{freq:g}",
           "--pcf-allow-unconstrained",
           "--report", repf,
           "--write", f"_{top}_placed.json",
           "--timing-allow-fail",
           "-q"]
    r = core.run_tool(cmd, cwd, timeout=timeout)

    rep = {}
    path = os.path.join(cwd, repf)
    try:
        with open(path, encoding="utf-8") as f:
            rep = json.load(f)
    except Exception:
        rep = {}

    util = rep.get("utilization") or {}
    lc = (util.get("ICESTORM_LC") or {})
    io = (util.get("SB_IO") or {})
    fmax = rep.get("fmax") or {}

    achieved = None
    constraint = None
    clock_net = None
    if fmax:
        clock_net, info = next(iter(fmax.items()))
        info = info or {}
        try:
            achieved = float(info.get("achieved"))
        except (TypeError, ValueError):
            achieved = None
        try:
            constraint = float(info.get("constraint"))
        except (TypeError, ValueError):
            constraint = None

    timing_met = None
    if achieved is not None:
        timing_met = achieved >= (constraint if constraint is not None else freq)
    crit = _pick_critical(rep)
    ok = bool(r["ok"]) and bool(rep)
    placed = os.path.join(cwd, f"_{top}_placed.json")
    if not os.path.exists(placed):
        placed = None
    strict = os.environ.get("COAL_PNR_STRICT", "").lower() in ("1", "true", "yes")
    if strict and timing_met is False:
        ok = False

    out = {
        "stage": "pnr",
        "ok": ok,
        "device": (device or DEVICE).lower(),
        "package": package or PACKAGE,
        "target_mhz": freq,
        "fmax_mhz": round(achieved, 1) if achieved is not None else None,
        "timing_met": timing_met,
        "timing_note": (None if achieved is not None
                        else "no register-to-register timing path"),
        "lc_used": lc.get("used"),
        "lc_available": lc.get("available"),
        "io_used": io.get("used"),
        "io_available": io.get("available"),
        "clock_net": clock_net,
        "critical_path": crit,
        "placed_json": placed,
        "run": r,
        "errors": [] if ok else [r["out"][-2500:]],
    }
    return out


def summary_line(stage: dict) -> str:
    """One-line human summary for reports."""
    if stage.get("skipped"):
        return "pnr      skipped (nextpnr unavailable)"
    if not stage.get("ok"):
        return "pnr      FAIL"
    bits = [f"{stage.get('device')}/{stage.get('package')}"]
    if stage.get("lc_used") is not None:
        bits.append(f"LC {stage['lc_used']}/{stage.get('lc_available')}")
    if stage.get("fmax_mhz") is not None:
        bits.append(f"Fmax {stage['fmax_mhz']:.1f} MHz")
        ticks = "met" if stage.get("timing_met") else "MISSED"
        bits.append(f"timing {ticks} @ {stage.get('target_mhz'):g} MHz")
    else:
        bits.append("timing n/a")
    return "pnr      ok (" + ", ".join(bits) + ")"
