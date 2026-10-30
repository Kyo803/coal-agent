"""High-level chip build: deterministic-first, model for novel logic.

Policy (chosen deliberately):
  1. If the request names a known block, use the deterministic generator —
     it is correct by construction and still goes through the same gate.
  2. Otherwise ask the local model, then run the gate and feed any errors
     back for a bounded number of repair rounds.
"""
from __future__ import annotations

import re

from . import compositions, core, designs, flow
from . import model as M

_NOVEL_ONLY = (
    r"\b(spi|i2c|arbiter|round.?robin|crc|"
    r"barrel\s+shifter|async\s+fifo|cdc|clock\s+domain)\b")

_KNOWN = [
    (r"\bbcd\b", "bcd_counter", {}),
    (r"\b(7.?seg|seven.?seg|segment\s+decoder)\b", "seg7", {}),
    (r"\b(priority\s+enc|prio\s*enc|8.?to.?3)\b", "prio_enc8", {}),
    (r"\bgray\b", "gray4", {}),
    (r"\b(multiplier|multipli|4x4\s+mult|mult4)\b", "mult4", {}),
    (r"\b(adder.?subtractor|addsub|add/sub)\b", "addsub", {}),
    (r"\b(uart|serial)\b.*\b(rx|receiv)", "uart_rx", {}),
    (r"\b(uart|serial\s+transmit|rs-?232)\b", "uart_tx", {}),
    (r"\b(fifo|queue|elastic\s+buffer)\b", "fifo", {}),
    (r"\b(vga|video\s+timing|hsync)\b", "vga_timing", {}),
    (r"\b(register\s*file|regfile)\b", "regfile", {}),
    (r"\b(clock\s+divider|clkdiv|clock\s+div)\b", "clkdiv", {}),
    (r"\b(alu|arithmetic\s+logic)\b", "alu4", {}),
    (r"\b(comparator|magnitude\s+compar|compare)\b", "comparator", {}),
    (r"\b(pwm|pulse\s*width)\b", "pwm", {}),
    (r"\b(debounc\w*|button\s+debounc\w*)\b", "debounce", {}),
    (r"\b(counter|count(er)?\s+up)\b", "counter", {}),
    (r"\b(shift\s*register|shiftreg|sipo|piso)\b", "shiftreg", {}),
    (r"\b(fsm|state\s+machine|traffic\s+light)\b", "fsm3", {}),
]


def detect_block(spec: str):
    low = (spec or "").lower()
    # things we do NOT have a deterministic generator for must go to the
    # model, otherwise we would silently build a different chip and call it
    # a pass.
    if re.search(_NOVEL_ONLY, low):
        return None, {}
    for pat, kind, params in _KNOWN:
        if re.search(pat, low):
            p = dict(params)
            m = re.search(r"(\d+)\s*[- ]?bit", low)
            if m and kind in ("counter", "shiftreg", "pwm"):
                p["width"] = int(m.group(1))
            if kind == "uart_tx":
                d = re.search(r"clks?_per_bit\s*[=: ]\s*(\d+)", low)
                if d:
                    p["clks_per_bit"] = int(d.group(1))
            if kind == "uart_rx":
                d = re.search(r"clks?_per_bit\s*[=: ]\s*(\d+)", low)
                if d:
                    p["clks_per_bit"] = int(d.group(1))
            if kind == "fifo":
                d = re.search(r"(\d+)\s*[- ]?(deep|entries|words)", low)
                if d:
                    p["depth"] = int(d.group(1))
            if kind == "regfile":
                n = re.search(r"(\d+)\s*(register|reg)s?\b", low)
                if n:
                    p["depth"] = int(n.group(1))
            if kind == "clkdiv":
                dv = re.search(r"(?:divide|divider|div)\s*(?:by)?\s*(\d+)",
                               low)
                if dv:
                    p["div"] = int(dv.group(1))
            return kind, p
    return None, {}


def _errors_text(rep: dict) -> str:
    parts = []
    for stage, v in (rep.get("stages") or {}).items():
        if v.get("ok"):
            continue
        for e in (v.get("errors") or []):
            parts.append(f"[{stage}] {e}")
    return "\n".join(parts)[:4000]


def _attach_views(rep: dict, name: str) -> dict:
    """Generate the 2D/3D views for a design that passed the gate."""
    if not rep.get("ok"):
        return rep
    try:
        from . import views as V
        cwd = rep.get("cwd") or flow.workspace(name)
        top = rep.get("design")
        area = rep.get("area") or {}
        stats = {"cells": area.get("cells") or 0,
                 "ffs": area.get("ffs") or 0,
                 "lc_used": area.get("lc"),
                 "lc_available": 7680,
                 "fmax_mhz": area.get("fmax_mhz"),
                 "timing_met": area.get("timing_met"),
                 "device": (rep.get("pnr") or {}).get("device"),
                 "package": (rep.get("pnr") or {}).get("package"),
                 "cell_types": rep.get("cell_types") or {}}
        rep["views"] = V.make_all(cwd, top, stats,
                                  formats=("glb", "fbx", "png"))
    except Exception as e:
        rep["views_error"] = str(e)[:300]
    return rep


def build(name: str, spec: str = "", kind: str | None = None,
          params: dict | None = None, max_repairs: int = 3,
          force_model: bool = False, make_views: bool = True) -> dict:
    """Build a chip block and verify it. Returns the verification report."""
    rep = _build_inner(name, spec, kind, params, max_repairs, force_model)
    if make_views:
        _attach_views(rep, name)
    return rep


def _build_inner(name: str, spec: str, kind: str | None,
                 params: dict | None, max_repairs: int,
                 force_model: bool) -> dict:
    if not kind and not force_model:
        from . import compositions
        comp = compositions.match(spec)
        if comp is not None:
            rep = flow.build_composition(comp, name=name)
            rep["source"] = "composition"
            rep["spec"] = spec
            return rep
        dk, dp = detect_block(spec)
        if dk:
            kind, params = dk, (params or dp)
            rep = flow.build_block(name, kind, **(params or {}))
            rep["source"] = "deterministic"
            rep["spec"] = spec
            return rep

    if kind:
        rep = flow.build_block(name, kind, **(params or {}))
        rep["source"] = "deterministic"
        rep["spec"] = spec
        return rep

    # a clearly multi-block request with no template: let the model pick the
    # graph (never the RTL), then validate it deterministically.
    if compositions.looks_composed(spec):
        from . import planner
        pcomp, _perr = planner.plan(spec)
        if pcomp is not None:
            rep = flow.build_composition(pcomp, name=name)
            rep["source"] = "planned"
            rep["spec"] = spec
            return rep

    # model path
    gen = M.generate_rtl(spec)
    if not gen.get("ok"):
        return {"design": name, "ok": False, "source": "model",
                "spec": spec, "errors": [gen.get("reason", "generation failed")],
                "stages": {}}

    rep = flow.build_design(name, gen["rtl"], top=gen.get("top"))
    rep["source"] = "model"
    rep["spec"] = spec
    rep["model"] = gen.get("model")
    tries = 0
    while not rep.get("ok") and tries < max_repairs:
        errs = _errors_text(rep)
        if not errs:
            break
        tries += 1
        fx = M.repair_rtl(gen["rtl"], gen.get("top") or name, errs,
                          model=gen.get("model"))
        if not fx.get("ok"):
            break
        gen["rtl"] = fx["rtl"]
        rep = flow.build_design(name, gen["rtl"], top=gen.get("top"))
        rep["source"] = "model+repair"
        rep["spec"] = spec
        rep["model"] = gen.get("model")
        rep["repairs"] = tries
    return rep
