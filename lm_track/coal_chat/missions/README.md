# Coal Silicon Lab — Extreme Mission Catalog

*Coal Silicon Lab: the owned chip/Verilog engineering pipeline of
`Coal-35B-A3B-Coal` (a Coal branded build of Qwen3.6-35B-A3B).*

Comprehensive, interlocking build projects for the autonomous builder.
Contract-first: each spec declares its own file manifest and (for HDL)
the exact module ports, so multi-module systems stay deterministic.

Drive them with:

```
coal.py --missions            # list
coal.py --mission forge-mesh  # build one
```

or from code: `from builder import build; build.generate_mission("helios-16")`.

## The family

| Mission | Stack | What it builds |
|---|---|---|
| `helios-16` | hdl | **16-bit CPU**: ALU, 16x16 regfile, 3-stage control, program+data memory; runs 5+3, testbench prints `HELIOS16:PASS` |
| `meridian-16` | hdl | **64K x 16 static RAM** chip (byte enables, tri-state) + testbench -> `MERIDIAN:PASS` |
| `vision-2` | hdl | **2-bit GPU chip**: 64x32 framebuffer, VGA-ish timing, 8x8 font ROM text mode -> `VISION2:PASS` |
| `aldra-asm` | cpp | **Assembler** for the HELIOS-16 ISA (two-pass, labels, hex/bin output) -> `ALDRA:PASS` |
| `tess-emu` | cpp | **Emulator** that executes HELIOS-16 machine code (loads .hex, runs 5+3) -> `TESS:PASS` |
| `parallax-3d` | typescript | **Ray-traced 3D renderer** (pure TS, spheres + checker floor, reflections) that also writes `dist/output.ppm` |
| `forge-mesh` | python | **Procedural 3D modeler**: value-noise terrain -> `mesh.obj` + `mesh.stl` + shaded `preview.ppm` (stdlib only) |

They form a workflow: **assemble (`aldra-asm`) → run on silicon (`helios-16`) or
software (`tess-emu`)** with `meridian-16` as memory and `vision-2` as the
display, plus **3D** (parallax/forge) as a separate extreme track.

## Mission JSON format

```jsonc
{
  "name": "...", "title": "...", "stack": "hdl|cpp|python|typescript",
  "description": "...", "context": "...",
  "manifest": [
    {"path": "alu.v", "purpose": "...", "ports": "input clk, output [15:0] y"}
  ],
  "criteria": ["file:...", "runs:...", "contains:..."]
}
```

## Status (from live runs)

| Mission | Result |
|---|---|
| `meridian-16` | ✅ **PASS** — fully autonomous: 35B generated RAM + testbench, builder mechanically patched a module-name mismatch, compiled, testbench `MERIDIAN:PASS`, **port contract verified** |
| `forge-mesh` | ✅ **PASS** — generated/kept code, compiled, ran, produced real `mesh.obj`/`mesh.stl`/`preview.ppm` (`FORGE:PASS`) |
| `tess-emu` | ⏳ attempted — generator landed a C weakness (unbalanced tail); queued for retry |
| `helios-16`, `vision-2`, `aldra-asm`, `parallax-3d` | ⏳ queued |

## Honest expectations

The builder generates each unit with the 35B, freezes verified units,
compiles/tests in the sandbox, and diagnoses/fixes iteratively; HDL modules
are additionally verified against their declared ports after the build.
Smaller missions typically complete; flagship integrated systems (the CPU)
may land as an honest attempt with the failed modules reported — the loop
refuses to fake a pass.

## Bugs the missions surfaced (and fixed)

- thinking was 34× slower per unit — disabled for code generation
- `_extract_code` didn't recognise `c`/`cpp` fences (stray line leaked)
- HDL testbench module-name mismatch → auto-`_hdl_patch`
- shared testbench was passed to iverilog twice → tester deduped
- cpp `Makefile` referencing missing source → auto-`_cpp_patch`
- mission runner now keeps already-good units by declared exports