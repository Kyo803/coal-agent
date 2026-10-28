"""Build + verify pipelines for chip designs."""
from __future__ import annotations

import json
import os
import shutil
import time

from . import core, designs, pnr

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
WORK = os.path.join(os.path.expanduser("~"), ".rox", "work", "chips")


def workspace(name: str) -> str:
    p = os.path.join(WORK, name)
    os.makedirs(p, exist_ok=True)
    return p


def _write(cwd, fn, text):
    p = os.path.join(cwd, fn)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return p


def _verilog(cwd):
    return sorted(f for f in os.listdir(cwd)
                  if f.lower().endswith((".v", ".sv")))


def verify_dir(cwd: str, top: str, tb: str | None = None,
               gold_rtl: str | None = None, gold_top: str | None = None,
               keep: bool = True, enable_pnr: bool = True) -> dict:
    """Run the full gate on the Verilog files in `cwd`."""
    all_files = _verilog(cwd)
    # synthesizable RTL only: yosys cannot parse $fatal/$display testbenches
    rtl = [f for f in all_files
           if not f.startswith("tb_") and not f.endswith("_tb.v")]
    if not rtl:
        return {"design": top, "ok": False, "stages": {},
                "errors": ["no RTL files"]}
    stages = {}
    stages["lint"] = core.lint(rtl, cwd, top)
    if tb:
        stages["sim"] = core.simulate(all_files, cwd, tb)
    stages["synth"] = core.synthesize(rtl, cwd, top)
    stages["formal"] = core.formal(rtl, cwd, top)
    if enable_pnr:
        stages["pnr"] = pnr.place_and_route(rtl, cwd, top)
    if gold_rtl:
        gdir = os.path.join(cwd, "_golden")
        os.makedirs(gdir, exist_ok=True)
        gfiles = []
        for src in ([gold_rtl] if isinstance(gold_rtl, str) else gold_rtl):
            dest = os.path.join(gdir, os.path.basename(src))
            shutil.copyfile(src, dest)
            gfiles.append(dest)
        stages["equiv"] = core.equivalence(
            gfiles, gold_top or top, [os.path.join(cwd, f) for f in rtl],
            top, cwd)
    rep = core.report(top, stages, cwd)
    if not keep:
        for f in os.listdir(cwd):
            if f.endswith((".vvp", ".out")):
                try:
                    os.remove(os.path.join(cwd, f))
                except Exception:
                    pass
    return rep


def build_block(name: str, kind: str, reference: bool = False,
                **params) -> dict:
    """Generate a deterministic block, verify it, and (optionally) prove it
    equivalent to the golden corpus copy."""
    cwd = workspace(name)
    for f in _verilog(cwd):
        os.remove(os.path.join(cwd, f))
    blk = designs.generate_block(kind, **params)
    top = blk["top"]
    _write(cwd, f"{top}.v", blk["rtl"])
    _write(cwd, f"tb_{top}.v", blk["tb"])
    gold = None
    gold_top = None
    if reference:
        gp = os.path.join(GOLDEN, f"{top}.v")
        if os.path.exists(gp):
            gold, gold_top = gp, top
    rep = verify_dir(cwd, top, tb=f"tb_{top}", gold_rtl=gold,
                     gold_top=gold_top)
    rep["kind"] = kind
    rep["cwd"] = cwd
    return rep


def build_design(name: str, rtl: str, tb: str = "", top: str | None = None,
                 gold_rtl: str | None = None) -> dict:
    """Verify caller/model-provided RTL."""
    cwd = workspace(name)
    for f in _verilog(cwd):
        os.remove(os.path.join(cwd, f))
    if not top:
        import re
        m = re.search(r"\bmodule\s+([A-Za-z_]\w*)", rtl or "")
        top = m.group(1) if m else "top"
    _write(cwd, f"{top}.v", rtl)
    tbname = None
    if tb:
        tbname = f"tb_{top}"
        _write(cwd, f"{tbname}.v", tb)
    rep = verify_dir(cwd, top, tb=tbname, gold_rtl=gold_rtl,
                     gold_top=top if gold_rtl else None)
    rep["cwd"] = cwd
    return rep


def build_composition(comp, name: str | None = None,
                      make_views: bool = False) -> dict:
    """Emit, wire and verify a multi-block chip.

    Wiring is validated before anything is written; the emitted top module
    then goes through the same gate as a single block.
    """
    from . import compose as C

    blocks = C.generate_blocks(comp)
    problems = comp.validate(blocks)
    if problems:
        return {"design": comp.top, "ok": False, "stages": {},
                "source": "composition", "errors": problems[:20],
                "composition": {"name": comp.name,
                                "blocks": len(comp.instances),
                                "nets": len(comp.nets)}}

    cwd = workspace(name or comp.name)
    for f in _verilog(cwd):
        os.remove(os.path.join(cwd, f))
    for fn, src in comp.emit_files(blocks).items():
        _write(cwd, fn, src)

    tbname = f"tb_{comp.top}" if comp.tb else None
    rep = verify_dir(cwd, comp.top, tb=tbname)
    rep["cwd"] = cwd
    rep["source"] = "composition"
    rep["proof"] = ("system-testbench (functional)" if comp.tb
                    else "structural only (no system testbench)")
    rep["composition"] = {
        "name": comp.name,
        "blocks": [{"inst": i.name, "kind": i.kind, "module": blocks[i.kind]["top"],
                    "params": i.params} for i in comp.instances.values()],
        "nets": [{"name": n.name, "width": n.width,
                  "top": n.top_dir, "driver": (n.drivers or [None])[0],
                  "sinks": list(n.sinks)} for n in comp.nets.values()],
    }
    if make_views:
        rep = B_attach_views(rep, name or comp.name)
        try:
            from . import views as V
            png = os.path.join(cwd, f"{comp.top}-composition.png")
            rep.setdefault("views", {})["composition"] = \
                V.composition_diagram(rep.get("composition") or {}, png)
        except Exception as e:
            rep["views_error"] = str(e)[:200]
    return rep


def B_attach_views(rep: dict, name: str) -> dict:
    """Attach 2D/3D views (shared with build())."""
    from .build import _attach_views
    return _attach_views(rep, name)
