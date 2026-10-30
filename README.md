# Coal — the AI that proves the chip works

**Nebius × NVIDIA hackathon submission.**

**Live project page: https://kyo803.github.io/coal-agent/**

Describe a chip in English. Coal writes the RTL, writes an **independent
reference model of the specification**, generates the testbench from that
model, and drives a real toolchain — lint, simulation, synthesis with ABC,
formal checks, and FPGA place-and-route with timing.

It does not tell you the chip works. **It proves it, or it fails the gate and
tells you why.**

![architecture](submission/assets/architecture.png)

---

## The problem

Every "AI writes Verilog" demo has the same hole: the model writes the design
*and* the test, so the test agrees with the bug. It looks correct and isn't.

Coal removes the model from the trust path.

## How it actually works

1. **Spec → design.** An LLM (Nebius Token Factory, NVIDIA-accelerated,
   default `nvidia/nemotron-3-super-120b-a12b`) proposes a design:
   either a **graph of known-good blocks** or an RTL draft.
2. **Spec → reference model.** A *Python model of the specification* is
   written independently. It never sees the RTL.
3. **Reference model → testbench.** `refsim` runs that model over a stimulus
   schedule and **generates the testbench**: same inputs, every output
   compared, every cycle.
4. **The gate.** `lint → sim → synth (ABC) → formal → place & route`.
   A chip is accepted only if all five pass.

Because the RTL and the expected behaviour come from two different processes,
a pass means *the design matches the specification* — not that it matches
itself. And the testbench is generated, so nobody can edit it into agreement
with a broken design.

## What is real today

| | |
|---|---|
| deterministic block library | **70 generators**, 39 with independent reference models |
| gate | lint · simulation (iverilog) · synth (yosys + ABC) · formal · **place & route (nextpnr-ice40)** |
| real timing | `stepper` 646 MHz · `segmux` 655 MHz · `reset_sync` 627 MHz · `cdc_sync` 627 MHz |
| multi-block chip | `uart_loopback` — 613 cells / 159 FF, **135.9 MHz**, byte in → byte out |
| catalogue | **44 / 50** designs built, each through the full gate |
| chip visibility | **2D floorplan from real nextpnr placement** (one region per module core) · VCD waveforms rendered to PNG and opened in **GTKWave** |
| security | authorisation-first method KB (235 entries) · SAST incl. C/C++ memory bugs · secret scan · **PE/ELF triage without executing the sample** |
| agent surface | **434 tools**, 22/22 live self-checks (incl. browser control, web search) |
| interface | OpenCode-style terminal UI with live thinking and tool trace |

![composition](submission/assets/composition.png)

*The UART loopback chip as Coal sees it: four blocks, eleven nets, every
connection width-checked before a line of Verilog is emitted.*

## Quickstart

```powershell
# 1. hosted inference (optional — falls back to local Ollama)
$env:NEBIUS_API_KEY = "..."        # Nebius Token Factory
$env:COAL_AGENT_MODEL = "nvidia/nemotron-3-super-120b-a12b"

# 2. build and verify a chip
cd Coal\agent
py -3.15 -c "import chipflow; r = chipflow.build('demo', spec='an 8-bit counter'); print(chipflow.summary_text(r))"

# 3. the terminal UI
tui\coal-tui.exe
```

The toolchain runs inside WSL; Coal detects it automatically and, if it is
missing, installs `iverilog verilator yosys gtkwave nextpnr-ice40` for you.

## Results, including the failures

[`submission/RESULTS.md`](submission/RESULTS.md) lists all 50 catalogue
designs: what each one is, what it is used for, and either its area/timing or
the exact reason it was rejected.

The failure taxonomy is the point, not an embarrassment:

| failure | count | meaning |
|---|---|---|
| testbench/elaboration | 5 | the model wrote a testbench that did not compile |
| formal equivalence | 1 | the design failed `check -assert` against its own netlist |

Every one of these 6 is a **model-generated** design. The 44 that pass include
8 that were originally model failures, then rebuilt as deterministic generator
blocks with independent reference models — `booth` (which exposed a real
signed-accumulator overflow), `quadrature` (a Verilog signedness bug where
`pos + step` with signed `step` and unsigned `pos` zero-extends −1 to +3), and
`crc8`, `cdc_sync`, `manchester_enc`, `reset_sync`, `uart_parity`, `bitrev`.

We report **44/50** because the gate refused the rest.

[`submission/BENCHMARK.md`](submission/BENCHMARK.md) measures the hosted model
directly: with the model writing both RTL and testbench it passed 0/6 of the
hardest designs (four failures were broken testbenches, not broken RTL); with
RTL alone against an independent reference-model testbench it passed 2/10
one-shot and 5/10 with up to two repairs.

## Why Nebius × NVIDIA

- The design model runs on **Nebius Token Factory** (OpenAI-compatible,
  NVIDIA-accelerated, default `nvidia/nemotron-3-super-120b-a12b`). The
  adapter is endpoint-agnostic: point `COAL_BASE_URL` at an **NVIDIA NIM**
  endpoint and the same agent uses it.
- Everything that *decides* runs locally and deterministically. No network
  dependency in the verification path — a demo cannot be derailed by Wi-Fi.
- The architecture is a statement about AI reliability: **the model proposes,
  the tools decide.**
- Nemotron-3 is a reasoning model, so by default we disable its reasoning
  trace (`reasoning_effort: none`) and spend the whole token budget on the
  Verilog. Trust comes from the gate, not from the model's chain of thought —
  and leaving reasoning on caused the model to exhaust its budget before
  emitting any code at all.

## Honest limits

- Place-and-route targets **iCE40 FPGA**, not an ASIC. The timing numbers are
  real; ASIC mapping is future work.
- 44/50, not 50/50.
- The local machine has no NVIDIA GPU; the GPU work happens in Nebius
  inference.

## Repository map

Start with the first row; the rest is supporting detail.

| Where | What you will find |
|---|---|
| [`README.md`](README.md) | this page: what Coal is, results, quickstart |
| [`submission/`](submission/) | judge writeup, architecture, all 50 results, benchmark, demo script, 3:2 gallery |
| [`agent/`](agent/) | the runtime: entry point, chip engine, tools, memory, TUI |
| [`agent/chipflow/`](agent/chipflow/) | blocks → gate → place & route → floorplan → waveforms |
| [`agent/docs/`](agent/docs/) | design notes, model card, evaluation, roadmap |
| [`desktop/`](desktop/) | native desktop app (Rust/Tauri shell + Go launcher + UI) |
| [`docs/`](docs/) | landing page (also the GitHub Pages site) |
| [`archive/`](archive/) | earlier experiments and training data, kept for provenance |

```text
submission/            judge-facing writeup and media
  ARCHITECTURE.md      the verification design in detail
  RESULTS.md           all 50 catalogue designs, passed and rejected
  BENCHMARK.md         Nemotron measurements, including failures
  DEMO.md              the 3-minute demo script
  assets/              diagrams, die map, 3D package, 3:2 gallery

agent/                 Python runtime
  coal.py              entry point (chat, JSON protocol, one-shot)
  coal_config.py       configuration (~/.coal/config.json)
  chipflow/            chip engine: generators, gate, P&R, waves, floorplan
  tools/               434 tool definitions and handlers
  memory/ board/       recall and the project board
  builder/ learning/   project build loop and self-directed study
  sandbox/ governance/ isolated Linux and resource safety
  tui/                 terminal UI (Go)
  docs/ data/ scripts/ notes, fixtures, setup scripts
  test_*.py            the test suite

desktop/               Tauri shell + Go launcher + terminal UI
docs/                  landing page (GitHub Pages)
archive/               history: legacy packages, neuromorphic track, training data
```

---

## Authorship

Copyright © 2026 **Zaim Khan (Coal)**. Licensed Apache-2.0.

See [NOTICE.md](NOTICE.md) for provenance (first public commit, repository of
record) and the attribution requirements anyone redistributing this work must
follow.

---

> "Anyone can make a model write Verilog. Coal makes it prove the chip
> works — or refuses to call it a chip."
