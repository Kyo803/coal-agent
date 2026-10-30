# Demo — 3 minutes, pre-recorded

Record at 1080p. Have the terminal at ~120 columns, dark theme, font size up
two notches. Cut every wait longer than ~2 seconds.

## Before recording

```powershell
# one command: reads the key, points at Nebius, sets COAL_NO_35B, starts the TUI
cd "C:\Users\gamel\OneDrive\Documents\Default Project\Coal\agent"
.\demo.cmd
```

If the key is not already in the environment, put it in
`%USERPROFILE%\.coal\nebius.key` (one line, no quotes) and `demo.cmd` will read
it. The header should show `nebius · nvidia/nemotron-3-super-120b-a12b`.

Warm the toolchain once so the first gate on camera is not slow:

```powershell
py -3.15 -c "import chipflow; chipflow.build_block('warmup','counter',width=8)"
```

Open `submission/RESULTS.md` in a second window (or `~/.coal/work/chips/_unique/UNIQUE_CHIPS.md`).

## Shot list

| t | action | narration |
|---|---|---|
| 0:00 | TUI open, header `nebius · Qwen2.5-Coder-32B` | "This is Coal. It designs chips — and it can prove them." |
| 0:10 | type `build a UART loopback chip`, hit enter | "I ask in English." |
| 0:15 | thinking lines stream, then `▶ chip_build` | "It plans, picks blocks, and calls real tools." |
| 0:25 | gate block appears: lint/sim/synth/formal/pnr ✓“ | "Lint, simulation, synthesis through ABC, formal checks — and place-and-route." |
| 0:40 | highlight `Fmax 135.9 MHz · 613 cells / 159 FF` | "That frequency came out of a real FPGA place-and-route run." |
| 0:50 | `ctrl+t` to hide thinking, `ctrl+o` to collapse tools | "Thinking and tool traces are toggleable." |
| 1:00 | open `assets/composition.png` | "Four blocks, eleven nets — every width checked before a line of Verilog." |
| 1:10 | open `assets/architecture.png` | "Here's the part that matters. The RTL and the expected behaviour are written by **different processes**." |
| 1:30 | open `RESULTS.md`, scroll | "Fifty designs. Forty-four passed. The rest were rejected — here's why." |
| 1:50 | point at a FAIL row (behaviour mismatch) | "One of these had inverted parity. The reference model caught it. The model that wrote it did not." |
| 2:10 | open `assets/die-map.png` + `assets/package-3d.png` | "Area map and a 3D package, generated from the same netlist." |
| 2:25 | back to TUI, type `what did the last batch prove?` | "And it can explain its own results." |
| 2:45 | title card | "Anyone can make a model write Verilog. Coal makes it prove the chip works — or refuses to call it a chip." |

## Commands that must be on screen

```powershell
# the proof, in one line
py -3.15 -c "import chipflow; r=chipflow.build('demo', spec='an 8-bit counter'); print(chipflow.summary_text(r))"

# the catalogue
py -3.15 -m chipflow.unique --limit 50 --model 7b --repairs 1

# the tool surface
py -3.15 tools_selftest.py
```

## If something fails on camera

Do not hide it. Say: *"This is the gate doing its job — that design was wrong,
and it was refused."* Then show the failure reason. That is the thesis of the
project; a failure is better footage than a pass.

## Do not say

- "It designs any chip" — it covers 44 of 50 catalogue entries today.
- "ASIC" — this is iCE40 FPGA place-and-route.
- "The AI wrote the testbench" — the testbench is *generated from an
  independent Python model*. That distinction is the whole project.
