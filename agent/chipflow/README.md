# chipflow — the chip engine

Turns a request into RTL, proves it, and draws it.

**Gate** (`core.py`, `flow.py`, `build.py`): lint (yosys + verilator) ·
simulation (iverilog/vvp, self-checking) · synthesis (yosys + ABC) ·
formal (equiv/induction) · place & route (nextpnr-ice40) with real
timing. A design only counts as built when every stage passes.

**Generators** (`designs.py`, `lib2.py`, `lib3.py`): 70 deterministic
blocks; 32 also have an independent Python reference model in `refsim.py`
that generates the testbench, so RTL and model are verified separately.

**Composition** (`compositions.py`, `compose.py`, `ports.py`): multi-block
chips (e.g. `uart_loopback` = fifo + rx + tx + ctl) with width-checked nets.

**Beyond the gate**
- `views.py` — RTL block diagram, gate schematic, die map, 3D package.
- `floorplan.py` — real 2D floorplan from nextpnr placement, one region
  per module core.
- `waves.py` — runs the testbench with VCD dumping, renders a waveform
  PNG, opens GTKWave.
- `pnr.py` — synthesis + nextpnr + timing report; also writes placement.

**Model-assisted** (`model.py`, `planner.py`): only for designs with no
deterministic generator; errors are fed back for bounded repair rounds.

**Batch** (`batch.py`, `unique.py`): autonomous runs over the catalogue.

Run from the agent directory:

```powershell
py -3.15 -c "import chipflow; r = chipflow.build('demo', spec='8-bit counter'); print(chipflow.summary_text(r))"
```
