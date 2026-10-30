"""Tests for the native chip flow (chipflow)."""
import json
import os

PASS = FAIL = 0


def ok(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")


def main():
    import chipflow
    from chipflow import core

    print("== 1. toolchain ==")
    av = core.available()
    ok("yosys available (native or yowasp)",
       bool(av.get("yosys")))
    print(f"     backend: {av.get('yosys_backend')}  "
          f"iverilog_compiles={core.iverilog_works()}")

    print("== 2. deterministic blocks ==")
    for kind, params, min_ffs in (("alu4", {}, 0),
                                  ("counter", {"width": 8}, 8),
                                  ("fsm3", {}, 3)):
        rep = chipflow.build_block(f"t_{kind}", kind, **params)
        st = rep["stages"]
        ok(f"{kind}: gate passes",
           rep["ok"] and st["lint"]["ok"] and st["synth"]["ok"]
           and st["formal"]["ok"])
        ok(f"{kind}: area reported", (rep["area"]["cells"] or 0) > 0)
        if min_ffs:
            ok(f"{kind}: {min_ffs} FFs", rep["area"]["ffs"] == min_ffs)

    print("== 3. equivalence vs golden ==")
    rep = chipflow.build_block("t_equiv", "alu4", reference=True)
    ok("alu4 proven equivalent to golden",
       rep["stages"].get("equiv", {}).get("ok") is True)

    print("== 4. 2D/3D views ==")
    cwd = rep["cwd"]
    from chipflow import views
    v = views.make_all(cwd, "alu4",
                       {"cells": rep["area"]["cells"],
                        "ffs": rep["area"]["ffs"],
                        "cell_types": rep["cell_types"]},
                       formats=("glb", "png"))
    for k in ("block", "schematic", "die_map", "3d_png", "3d_glb"):
        p = v.get(k)
        ok(f"{k} generated", isinstance(p, str) and os.path.exists(p))

    print("== 5. build() auto-detects the block ==")
    rep2 = chipflow.build("t_auto", spec="build a 16-bit counter",
                          make_views=False)
    ok("16-bit counter detected + verified",
       rep2["ok"] and rep2.get("source") == "deterministic"
       and rep2["area"]["ffs"] == 16)

    print("== 6. intent routing ==")
    from tools.intent import detect_intent
    ok("chip phrase routes to chip_build",
       detect_intent("design a UART transmitter").tool == "chip_build")
    ok("3d phrase still routes to generate_3d",
       detect_intent("make a 3D model of a robot").tool == "generate_3d")

    print("== 7. registry ==")
    from tools import specs
    names = [s["name"] for s in specs.by_category("chip")]
    ok("chip tools registered",
       {"chip_build", "chip_gate", "chip_tools", "chip_views"} <= set(names))

    print("== 8. place & route + timing ==")
    from chipflow import pnr
    if not pnr.available():
        print("     skipped (nextpnr-ice40 unavailable)")
    else:
        rep3 = chipflow.build_block("t_pnr", "counter", width=8)
        a3 = rep3["area"]
        ok("pnr stage passes", rep3["stages"]["pnr"]["ok"] is True)
        ok("mapped to iCE40 LCs", (a3.get("lc") or 0) > 0)
        ok("Fmax reported", (a3.get("fmax_mhz") or 0) > 0)
        ok("timing met at target", a3.get("timing_met") is True)
        ok("critical path captured",
           bool((rep3.get("pnr") or {}).get("critical_path")))
        rep4 = chipflow.build_block("t_pnr_comb", "alu4")
        ok("combinational: routed but timing n/a",
           rep4["stages"]["pnr"]["ok"] is True
           and rep4["area"].get("fmax_mhz") is None)

    print("== 9. composition (multi-block chips) ==")
    from chipflow import compose, compositions, ports as P
    blk = chipflow.generate_block("uart_tx")
    p = P.ports_of(blk["rtl"], blk["top"])
    ok("ports parsed (uart_tx)", p.get("data", {}).get("width") == 8
       and p.get("tx", {}).get("dir") == "output")
    comp = compositions.get("uart_loopback")
    blocks = compose.generate_blocks(comp)
    ok("uart_loopback wiring validates", comp.validate(blocks) == [])
    ok("uart_loopback has 4 blocks", len(comp.instances) == 4)
    rep5 = chipflow.build_composition(comp, name="t_uart_loopback")
    ok("composed chip passes the gate", rep5["ok"] is True)
    ok("composed chip gets P&R timing",
       (rep5["area"].get("fmax_mhz") or 0) > 0)
    rep6 = chipflow.build("t_loop_auto",
                          spec="build a UART loopback chip", make_views=False)
    ok("spec routes to composition",
       rep6.get("source") == "composition" and rep6["ok"])

    print("== 10. reference-model blocks ==")
    from chipflow import lib2
    ok("library has 32 reference-model blocks", len(lib2.BLOCKS) == 32)
    for kind in ("parity8", "lfsr8", "bin2bcd", "lzc"):
        rr = chipflow.build_block("tref_" + kind, kind)
        ok(f"{kind}: gate passes", rr["ok"] is True)
        ok(f"{kind}: simulated vs Python model",
           rr["stages"]["sim"].get("ok") is True)

    print("== 11. waveform + 2D floorplan ==")
    from chipflow import waves, floorplan
    rep7 = chipflow.build_block("t_wave", "counter8", make_views=False)
    ok("wave test design passes the gate", rep7["ok"] is True)
    d7 = os.path.dirname(rep7["path"])
    top7 = rep7.get("design") or "counter8"
    w = waves.capture(d7, top7, open_gui=False)
    ok("VCD produced by the simulator",
       w.get("ok") and w.get("vcd") and os.path.exists(w["vcd"]))
    ok("waveform PNG rendered",
       bool(w.get("png")) and os.path.exists(w["png"]))
    fp = floorplan.render_from_dir(d7, top7)
    ok("floorplan rendered from placement",
       fp.get("ok") and os.path.exists(fp.get("png") or ""))
    ok("floorplan knows the fabric size",
       (fp.get("info") or {}).get("cols") == 160
       and (fp.get("info") or {}).get("rows") == 48)

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
