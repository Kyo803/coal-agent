# ROX N — Chip Generation (`chipflow`)

_RTL build + verification + 2D/3D views, on the real toolchain inside WSL._

## Where the tools run

Windows **Smart App Control + WDAC (Device Guard)** block unsigned native
binaries, so the HDL toolchain runs **inside WSL** (Ubuntu 24.04), where
Linux executables are not subject to Windows code integrity:

| tool | version | role |
|---|---|---|
| `iverilog` / `vvp` | 12.0 | **simulation** of self-checking testbenches |
| `verilator` | 5.020 | lint (`--lint-only -Wall`) |
| `yosys` | 0.33 | synthesis, formal, equivalence |
| `abc` | yosys-abc | **area-accurate gate mapping** |
| `nextpnr-ice40` | 0.6 | FPGA place-and-route |
| `gtkwave` | 3.3.116 | waveforms |

`chipflow.backend` detects this automatically and routes every call through
WSL. With no distro present it falls back to **YoWASP yosys (WASM)**, which
can still synthesise and prove equivalence but has **no simulator and no
ABC** (pre-ABC gate counts, sim reported as skipped).

## The gate (nothing is "done" below this)

```
lint     yosys read + check -assert, verilator -Wall, iverilog -Wall
sim      iverilog + vvp; self-checking tb must print <MOD>:PASS
synth    yosys synth (ABC) + stat          -> gate cells / FFs / memories
formal   yosys check -assert               -> no latches, no comb loops
pnr      synth_ice40 + nextpnr-ice40       -> LCs, IO, Fmax, critical path
equiv    yosys equiv_make/equiv_simple     -> proven equal to the golden
report   JSON + human summary
```

## Place & route (real FPGA timing)

Every chip is taken through **yosys `synth_ice40` → `nextpnr-ice40`**, so the
gate reports what actually fits and how fast it runs:

| field | meaning |
|---|---|
| `LC` | logic cells used of the device capacity (HX8K = 7680) |
| `IO` | pins used |
| `Fmax` | achieved clock frequency (MHz) |
| `timing_met` | `Fmax >= target` |
| `critical_path` | slowest register-to-register path (ns, from → to) |

Combinational blocks are still placed and routed; their timing is reported as
`n/a` instead of failed. Configuration:

```
ROX_FPGA_DEVICE=hx8k|up5k|lp384   default hx8k
ROX_FPGA_PACKAGE=ct256            default ct256
ROX_PNR_FREQ=24                   target MHz (default 24)
ROX_PNR_STRICT=1                  make a timing miss FAIL the gate
ROX_NO_PNR=1                      skip place & route entirely
```

Example: `counter8` → 16 LCs, **365.2 MHz**; `uart_tx` → **136.9 MHz**;
`alu4` → routed, timing n/a (no clock).

## Deterministic blocks (correct by construction)

| kind | module | verified area |
|---|---|---|
| `alu` / `alu4` | 4-bit ALU + zero | 120 cells, 0 FF |
| `comparator` | magnitude comparator (gt/lt/eq) | 25 cells, 0 FF |
| `counter` | up counter, sync reset, enable, carry | 40 cells / 8 FF (8-bit) |
| `shiftreg` | load / serial shift | 16 cells / 8 FF |
| `fsm` / `fsm3` | 3-state FSM | 17 cells / 3 FF |
| `pwm` | duty-cycle comparator | 69 cells / 9 FF |
| `uart_tx` | UART transmitter | 166 cells / 34 FF |
| `uart_rx` | UART receiver (mid-bit sampling) | 287 cells / 41 FF |
| `fifo` | synchronous FIFO + full/empty/count | 199 cells / 82 FF (8x8) |
| `vga_timing` | 640x480@60 h/v timing | 255 cells / 20 FF |
| `regfile` | 2-read/1-write register file | 90 cells / 32 FF (4x8) |
| `clkdiv` | clock divider / tick | 9 cells / 3 FF |
| `bcd_counter` | BCD 0-9 counter + carry | 18 cells / 4 FF |
| `seg7` | 7-segment decoder (active low) | 32 cells / 0 FF |
| `prio_enc8` | 8-to-3 priority encoder + valid | combinational |
| `gray4` | binary → Gray converter | combinational |
| `mult4` | 4x4 unsigned multiplier | combinational |
| `stream_ctrl` | pop→start glue FSM for stream blocks | 3 cells / 1 FF |
| `addsub` | adder/subtractor + carry + overflow | 40 cells, 0 FF |
| `debounce` | button debouncer | 49 cells / 10 FF |
| `parity8` | byte parity, even/odd, error out | 8 cells (ref model) |
| `popcount4` | population count | 10 cells (ref model) |
| `bitrev8` | registered bit reversal | 8 cells / 8 FF (ref model) |
| `gray_counter` | Gray-code counter | 12 cells / 4 FF, 448 MHz |
| `johnson4` | Johnson counter | 5 cells / 4 FF, 627 MHz |
| `edge_detect` | rising/falling/both pulses | 7 cells / 4 FF, 655 MHz |
| `updown8` | up/down counter with load | 56 cells / 8 FF, 211 MHz |
| `lfsr8` | maximal-length LFSR | 35 cells / 8 FF, 390 MHz |
| `bin2bcd` | binary → 3-digit BCD (double dabble) | 118 cells |
| `prio16` | 16→4 priority encoder + valid | 84 cells |
| `satadd` | 8-bit saturating adder | 57 cells |
| `absval` | 8-bit absolute value + flags | 25 cells |
| `lzc` | leading-zero counter | 34 cells |
| `hamming_enc` | Hamming(7,4) encoder | 7 cells |

The last fourteen are verified against an independent Python model.

All pass lint + **simulation** + synth + formal + **place & route**.
`alu4` is additionally proven equivalent to the golden reference.

> **Faithfulness rule:** if a spec asks for something we do *not* have a
> generator for (SPI, I2C, arbiter, debounce, CRC, adder/subtractor…), the
> detector returns *no* block and the model builds it — it never silently
> substitutes a different chip and reports PASS.

## Backends (`chipflow/backend.py`)

The flow picks a backend automatically:

| backend | what you get |
|---|---|
| **wsl** | iverilog (sim), verilator (lint), yosys **+ ABC** (accurate area), nextpnr |
| native | only if the exe actually runs (blocked on this box) |
| **wasm** (YoWASP) | yosys only: synth (`-noabc`), formal, equivalence |

WSL is the full unblock and is **now active**: `Ubuntu-24.04` with the whole
toolchain installed. `chipflow` reports `"backend": "wsl"` and runs real
simulation and ABC-mapped synthesis. The installer (`setup_wsl.ps1`) enables
the Windows features, and a one-shot logon task (`ROX_WSL_Finish`) finishes
the distro setup after a real **Restart** (Fast Startup hides pending
feature installs from Shutdown).

## Model layer (composition + repair)

`chipflow/model.py` picks a local Ollama model by free RAM:

| free RAM | model |
|---|---|
| ≥ 13 GB | `qwen2.5-coder:14b` |
| ≥ 8 GB | `qwen2.5-coder:7b` |
| below | deterministic only |

Generation → gate → feed errors back → repair (bounded rounds). The model is
only trusted once the gate passes.

**Verified example:** asked for *"a 4-bit magnitude comparator with gt/lt/eq"*,
`qwen2.5-coder:14b` produced a module that passed lint + synth + formal on the
first attempt — **27 cells, 0 FFs**. (A comparator generator was also added
afterwards, so that block is now deterministic too.)

## 2D + 3D views (from the real netlist)

`chipflow/views.py` produces, for a verified design:

- **`*-block.png`** — RTL block diagram with ports
- **`*-schematic.png`** — gate-level schematic (layered, from `write_json`)
- **`*-die.png`** — area map by cell type
- **`*-package.png` / `.glb` / `.fbx`** — 3D die + substrate + pins

## Batch mode — ROX N designs a whole corpus

`chip_batch` (or `python -m chipflow.batch --limit 50`) builds a corpus of
designs unattended:

- **default corpus: 50 chips** — 41 parameterised deterministic blocks
  (counters 4–32 bit, FIFOs 8×4…32×16, UART TX/RX at 3 baud dividers,
  register files, VGA, PWM, comparators, shift registers, clock dividers)
  plus 9 novel specs the model must build (BCD counter, 7-segment, priority
  encoder, Gray, multiplier, adder/subtractor, arbiter, debouncer, SPI).
- **resumable** — results in `results.jsonl`; passed chips are skipped.
- **safe** — one at a time, BelowNormal priority, waits (not aborts) when
  free RAM is low, unloads the 14B between model chips, `STOP` file.
- **reports** `BATCH_REPORT.md` with per-chip result, source, cells, FFs.

**Full run (sim + ABC + place & route): 50/50 passed** — 47 deterministic,
2 model, 1 composition — **8426 mapped cells / 2677 FFs**, 36 clocked
designs all meeting timing, worst Fmax **135.9 MHz** (`uart_loopback_soc`).

> **Faithfulness rule:** if a spec asks for something we do *not* have a
> generator for (SPI, I2C, arbiter, CRC…), the detector returns *no* block and
> the model builds it — it never silently substitutes a different chip and
> reports PASS.

## Reference-model verification (why the chips are real)

The failure mode of "let the model write everything" is that the RTL and the
testbench are both guesses and agree with each other. `chipflow/refsim.py`
removes that:

```
spec ──► human/library RTL  ─┐
                             ├─► same stimulus, every output checked every cycle
spec ──► Python model      ──┘
```

1. The **Verilog** is written by the generator library.
2. A **Python model of the specification** is written separately.
3. `refsim.build_tb()` runs the model over a stimulus schedule and *emits a
   testbench* that drives the DUT with the same inputs and compares every
   output, every cycle.

The two sides are produced by different means, so a pass means the RTL and
the specification agree — not that the RTL agrees with itself.

Adding a block is mechanical and safe:

```python
def parity8():
    rtl = """module parity8 (...); assign err = (^data) ^ odd; endmodule"""
    class M:                      # the specification, in Python
        def step(self, i):
            return {"err": bin(i["data"]).count("1") % 2 ^ i["odd"]}
    stim = [{"data": d, "odd": o} for d in range(256) for o in (0, 1)]
    return _build("parity8", rtl, M(), stim, clocked=False)
```

Every block in `chipflow/lib2.py` follows that shape, and the testbench is
generated — nobody can "fix" the test to make a broken design pass.

### Chips ROX N can build today

`chip_unique` is **deterministic-first**: if the catalogue entry has a
generator it is built from the library (correct by construction); only the
rest is attempted by the model, and still has to pass the same gate.

```
DETERMINISTIC = {"bcd2seg": ("seg7", {}), "lfsr8": ("lfsr8", {}),
                 "parity": ("parity8", {}), "graycounter": ("gray_counter", {}),
                 "johnson": ("johnson4", {}), "edge_detect": ("edge_detect", {}),
                 "updown": ("updown8", {}), "debounce": ("debounce", {"width": 8}),
                 "clkdiv3": ("clkdiv", {"div": 3})}
```

Coverage grows one safe block at a time; the model is never trusted with RTL
that has no independent reference.

## Terminal UI (`rox_tui/`)

An OpenCode-style chat interface lives in `rox_tui/` (Go + bubbletea):

```powershell
cd lm_track\rox_chat\rox_tui
.\rox-tui.exe                 # full-screen chat
.\rox-tui.exe -selftest       # headless protocol check
```

It drives `rox.py --json-repl`: one long-lived agent session, one JSON object
per prompt on stdin, newline-delimited events on stdout
(`ready · start · thinking · token · tool · answer · done · error`).

Layout: a header with the active model, a scrolling transcript (user, streamed
answer, tool calls with their output, thinking in dim italics), a status line
with a spinner and elapsed time, and a bordered input box.

Keys: `enter` send · `ctrl+c` interrupt (or quit when idle) · `pgup/pgdn`
scroll · `ctrl+d` quit · **`ctrl+t` show/hide thinking** · **`ctrl+o`
show/hide tool output** · **`ctrl+w` install the WSL toolchain**.

Thinking is shown by default and can be hidden per session; tool output is
shown by default and collapses to one line.

**WSL is automatic.** On start the TUI asks `chipflow.backend` what is
available. If the backend is not `wsl`, it launches `setup_wsl.ps1` elevated
(once — it drops a marker in `~/.rox/wsl_install_attempted`) and tells you if
a reboot is required. `setup_wsl.ps1` now handles a **fresh machine**: if the
old sandbox disk is gone it runs `wsl --install -d Ubuntu-24.04 --no-launch`
and then installs `iverilog verilator yosys gtkwave nextpnr-ice40`.

The TUI always sets `ROX_NO_35B=1` for its child, so a chat can never try to
load the 19.7 GB model.

## Tool self-test (`tools_selftest.py`)

```powershell
py -3.15 tools_selftest.py            # audit + probe + live
py -3.15 tools_selftest.py --live-only
```

Three phases:

1. **AUDIT** — all ~430 specs: name, description, params, required args,
   handler wiring, duplicates. No side effects.
2. **PROBE** — every read-only tool is really invoked with arguments.
   Mutating / cloud / git-write / desktop-bound tools are skipped by policy
   (they would change the machine).
3. **LIVE** — end-to-end: filesystem round trip, glob/ripgrep, web search,
   web fetch, browser (navigate, tabs, snapshot, screenshot, console),
   knowledge search, the chip gate and a full chip build, 3D generation,
   memory, board and system status.

Current result: **429 tools, 422 clean; 45 probes ok, 0 probe errors;
22/22 live checks passed** (3 are native core tools, not executor tools).

Two real bugs were found and fixed by this:

- `web_fetch` failed on every HTTPS URL (`CERTIFICATE_VERIFY_FAILED`) — it
  now uses certifi's CA bundle.
- the browser died between tool calls: `sync_playwright()` was stored in a
  local (garbage-collected) and every tool call ran on a **new thread**, while
  Playwright's sync objects are thread-bound. The executor now uses one
  persistent worker thread and Playwright is shut down cleanly at exit.

## Composition (multi-block chips)

`chipflow/compose.py` wires verified blocks into one chip. The model never
writes block RTL here — it may only choose the graph.

```python
from chipflow.compositions import get
chipflow.build_composition(get("uart_loopback"))
```

Wiring is checked **before** anything is emitted:

- every endpoint must be a real instance port
- widths must match exactly (no silent truncation)
- every input driven, exactly one driver per net, one clock/reset domain

The composed top then goes through the *same* gate as a single block, with a
system testbench that proves the whole chip:

| composition | blocks | proof |
|---|---|---|
| `counter_cmp` | counter8 + cmp8 | comparator tracks the counter — 66 cells, 365 MHz |
| `uart_loopback` | uart_rx + fifo8x8 + uart_tx + stream_ctrl | a byte sent on `serial_in` comes back on `serial_out` — **613 cells / 159 FF, 135.9 MHz** |

`build("build a UART loopback chip")` routes here automatically.

### Planned compositions (the model chooses the graph)

If a spec clearly asks for several blocks and **no template matches**, the
local model is asked for a **graph — never RTL**:

```json
{"blocks": [{"inst": "rx", "kind": "uart_rx"},
            {"inst": "fifo", "kind": "fifo", "params": {"width": 8, "depth": 8}}],
 "nets": [{"name": "rx_data", "driver": "rx.data", "sinks": ["fifo.din"]}]}
```

The graph is validated deterministically (real ports, exact widths, one
driver per net, every input driven) and corrected for up to 2 rounds by
feeding the errors back. A planned chip is reported with

```
proof  structural only (no system testbench)
```

so it is never confused with a curated composition, which carries
`proof  system-testbench (functional)`.

Trigger rule: ≥2 block keywords **and** a composition marker ("loopback",
"buffers", "feeds", "pipeline", "->", …). A single-block spec such as
*"a debouncer with an 8-bit counter"* therefore still goes to the
deterministic generator, not the planner.

> **Why a controller block:** the FIFO's `dout` is registered (valid the cycle
> *after* `rd`), so `stream_ctrl` pops, waits one cycle, then pulses `start`.
> Simulation caught this exact mismatch on the first attempt.

## Tools

| tool | what |
|---|---|
| `chip_build` | build + verify (+ views). Known blocks deterministic; else model+repair |
| `chip_gate` | run the gate on an existing Verilog directory |
| `chip_tools` | toolchain status, model choice, block list |
| `chip_views` | regenerate the 2D/3D views |
| `chip_batch` | run/check/stop a batch of designs (`action=run|status|stop`) |
| `chip_unique` | 50 unique chips designed by ROX N (RTL + testbench each) |

Plain language works: *"build an 8-bit counter"*, *"design a UART transmitter"*.

## Unique chips (`chipflow/unique.py`)

`chip_unique` gives ROX N a catalogue of **50 distinct, useful designs**
(decoders, CRC, Hamming, Manchester, quadrature, debounce, watchdog, timers,
PWM with dead-time, servo/stepper sequencers, FSMs, SPI, stack, program
counter, Booth multiplier, SAR ADC…). For each one:

1. the model writes the **RTL** from the specification
2. a **second, independent pass** writes the **testbench** from the spec and
   the port list only — it never sees the RTL, so it checks the
   specification instead of mirroring a bug
3. the chip must pass the full gate (lint + simulation + synthesis + formal +
   place & route); a failure repairs the RTL against the frozen testbench

Because the two artifacts are written independently, a chip that passes has
been checked against something other than itself — that is the point.

```
py -3.15 -m chipflow.unique --limit 50 --model 7b --repairs 1
chip_unique action=status          # summary table
chip_unique action=run model=7b
```

Results and the per-chip write-up land in
`~/.rox/work/chips/_unique/UNIQUE_CHIPS.md` (what each chip is, what it is
used for, area, Fmax, proof stages, or the reason it failed).

**Why the 7B for this run:** on this CPU the 14B spends ~8 min per call
(~5 tok/s), which would turn 50 chips into an all-night job; the 7B does the
same call in ~60-80 s and leaves ~9 GB free. The 14B remains the model for
hard, single designs.

## Outputs

Everything lands in `~/.rox/work/chips/<design>/`:

```
counter8.v  tb_counter8.v  counter8-report.json
counter8-block.png  counter8-schematic.png  counter8-die.png
counter8-package.png  .glb  .fbx
```

Composed chips add the real instance graph:

```
uart_loopback.v (emitted top)  uart_rx.v  fifo8x8.v  uart_tx.v  stream_ctrl.v
tb_uart_loopback.v  uart_loopback-composition.png
```

The report JSON now carries `area.lc`, `area.io`, `area.fmax_mhz`,
`area.timing_met`, and `pnr.critical_path`.

## Honest limitations

- **Simulation now runs** (iverilog 12 inside WSL) and caught two real
  testbench races that formal analysis could never see — both fixed.
- **ABC mapping is active**, so reported area is post-ABC gate count
  (`alu4`: 120 pre-ABC → **105** mapped cells).
- **Novel complex designs** (a full CPU) will need many repair rounds with a
  14B model; deterministic blocks are the reliable path.
- **FPGA place-and-route** is installed (`nextpnr-ice40`) but not yet wired
  into the flow.
