# RECORD CARD — 3 minutes, one take

Read this off a second screen. Do not memorise it.

---

## Pre-flight (2 minutes, before you hit record)

```powershell
cd "C:\Users\gamel\OneDrive\Documents\Default Project\Coal\lm_track\coal_chat"
.\demo.cmd
```

Check the header says **`nebius · nvidia/nemotron-3-super-120b-a12b`**.

Toolchain is already warmed — do **not** re-warm.

Window: 120 columns, dark theme, font +2. Close Slack, close this chat.

---

## Beats

| time | do this | say this |
|---|---|---|
| **0:00** | TUI on screen, cursor blinking | “This is Coal. It designs chips — and it can prove them.” |
| **0:08** | type: `build a 4-bit gray to binary converter chip` | “I ask in English.” |
| **0:15** | thinking streams, then the `chip_build` tool row | “It plans, then calls real tools.” |
| **0:25** | gate block appears: lint / sim / synth / formal / pnr | “Lint, simulation, synthesis through ABC, formal — and real place-and-route.” |
| **0:40** | point at `PASS` + `cells=3` | “Three cells. Every stage passed.” |
| **0:50** | **the money shot** — type: `rebuild it but the output is inverted` | “Now watch what happens when it's wrong.” |
| **1:00** | gate shows `sim FAIL` | “The gate rejected it. Not the model's opinion — an independent Python model of the spec disagreed.” |
| **1:15** | let the repair run, then PASS | “It read the error, fixed the RTL, and passed.” |
| **1:30** | `ctrl+t` then `ctrl+o` | “Thinking and tool traces are toggleable.” |
| **1:40** | open browser tab: **kyo803.github.io/coal-agent** | “Here is the project page.” |
| **1:55** | scroll to the benchmark table | “Nemotron passed 6 of 6 novel designs first try. On harder ones, 2 of 10 — until repair took it to 5 of 10.” |
| **2:15** | open `submission/assets/gallery/die-map-3x2.png` | “Die map, from the same netlist.” |
| **2:25** | open `package-3d-3x2.png` | “And a 3D package.” |
| **2:35** | back to terminal | “The model proposes. The tools decide.” |
| **2:50** | title card / hold on the repo URL | “Anyone can make a model write Verilog. Coal makes it prove the chip works — or refuses to call it a chip.” |

---

## Rules that matter

- **Under 3:00.** Judges are not required to watch past it. Aim 2:50.
- **No music, no third-party trademarks** on screen. Clean desktop.
- 1080p, terminal readable at 720p.
- Cut any wait longer than ~2 seconds in the edit.

## If something fails on camera

**Do not hide it.** Say:

> “This is the gate doing its job — that design was wrong, and it was refused.”

That is the thesis. A rejection is better footage than a pass.

## Do not say

- ✗ “It designs any chip” → it covers 44 of 50 catalogue entries
- ✗ “ASIC” → this is iCE40 FPGA place-and-route
- ✗ “The AI wrote the testbench” → the testbench is generated from an **independent Python model**

---

## Upload

1. YouTube → **Unlisted** (or Public). **No password, no age restriction.**
2. Title: `Coal — the AI that proves the chip works (Nebius × NVIDIA)`
3. Description: repo link + project page link
4. Copy the URL into the Devpost form.

Verify it plays in an **incognito window** before submitting.
