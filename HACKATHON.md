# Nebius Ã— NVIDIA â€” submission plan

**Deadline: this week. Compute: API-only (no local NVIDIA GPU).**

---

## 1. The pitch

> **Coal is an agentic EDA engine.** You describe a chip in English; it writes
> the RTL, writes an *independent reference model of the specification*,
> generates the testbench from that model, and drives a real toolchain â€”
> lint, simulation, synthesis with ABC, formal checks, and FPGA
> place-and-route with timing. It does not *claim* the chip works. It proves
> it, or it fails the gate and tells you why.

The model is the least trustworthy component and we treat it that way. That is
the differentiator: **generation is cheap, verification is the product.**

Why this fits Nebius Ã— NVIDIA: the specâ†’RTL model runs on **Nebius AI Studio**
(OpenAI-compatible, NVIDIA-accelerated inference); the verification stack runs
locally and deterministically. The agent decides *what* to build, the tools
decide *whether it is real*.

---

## 2. Demo (3 minutes, recorded)

| time | shot | what the judge sees |
|---|---|---|
| 0:00â€“0:20 | TUI, header | "Coal â€” local agent, 429 tools" |
| 0:20â€“0:50 | type *"build a UART loopback chip"* | thinking stream visible, then `chip_build` tool call |
| 0:50â€“1:30 | gate output | lint âœ“ sim âœ“ synth âœ“ formal âœ“ **pnr âœ“ 135.9 MHz**, 613 cells / 159 FF |
| 1:30â€“2:00 | `UNIQUE_CHIPS.md` | 50 designs, 17 verified, failure reasons for the rest |
| 2:00â€“2:30 | `-composition.png` + `-die.png` + package GLB | the chip as a block graph, an area map, a 3D package |
| 2:30â€“3:00 | architecture slide | independent reference model â†’ generated TB â†’ gate |

The money shot is `Fmax` from a real place-and-route run. Nobody fakes that.

**Pre-record it.** The machine is AMD-only and the toolchain takes seconds per
chip; a live demo risks dead air.

---

## 3. Sponsor integration (already implemented)

`chipflow/model.py` now has a provider switch:

```python
provider()  ->  "nebius" if NEBIUS_API_KEY else "ollama"
```

- **Nebius AI Studio**: `COAL_BASE_URL` (default `https://api.studio.nebius.com/v1`),
  `COAL_AGENT_MODEL` (default `Qwen/Qwen2.5-Coder-32B-Instruct`).
- Because it is OpenAI-compatible, the **same adapter can point at an NVIDIA
  NIM endpoint** â€” change the base URL and model name. That is a one-line
  change, not a rewrite.
- Without a key it falls back to local Ollama, so the demo never depends on
  the network.

```powershell
$env:NEBIUS_API_KEY = "..."                       # required for the sponsor angle
$env:COAL_AGENT_MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"
py -3.15 -c "from chipflow import model; print(model.provider_status())"
```

**Talking point for judges:** routing matters. A 32B hosted model writes the
first draft; the deterministic generator library and the reference model
decide what survives. We can show the same spec failing on a 7B and passing
on the hosted model â€” with the gate catching the difference.

---

## 4. What is already true (numbers to put on slides)

| claim | evidence |
|---|---|
| verified block library | **52 blocks**, 32 with independent Python reference models |
| every block passes | lint + simulation + synth (ABC) + formal + place-and-route |
| real timing | `counter8` 365 MHz, `edge_detect` 655 MHz, `uart_tx` 137 MHz |
| multi-block chip | `uart_loopback`: 613 cells / 159 FF, 135.9 MHz, byte in â†’ byte out |
| catalogue | **36/50** designs built, every one through the full gate |
| tool surface | **429 tools**, 22/22 live self-checks (incl. browser + web search) |
| verification design | TB generated from a Python model; the model never sees the RTL |

Honest framing beats overclaiming: say "17 of 50, and here is exactly why the
other 33 failed."

---

## 5. Deliverables checklist

- [ ] `README.md` at repo root aimed at a judge (90-second read)
- [ ] `ARCHITECTURE.md` + one diagram (spec â†’ model â†’ TB â†’ gate)
- [ ] `HACKATHON.md` (this file, trimmed)
- [ ] 3-minute video, 1080p, captions
- [ ] `NEBIUS_API_KEY` integration verified with a real key
- [ ] one-command demo: `py -3.15 -m chipflow.unique --limit 5` and the TUI
- [ ] results: `~/.coal/work/chips/_unique/UNIQUE_CHIPS.md` copied into the repo
- [ ] screenshots: composition PNG, die map, 3D package, TUI
- [ ] LICENSE + NOTICE (deps: yosys, iverilog, verilator, nextpnr, Ollama/Nebius)

## 6. Five-day timeline

| day | work |
|---|---|
| **1 (today)** | get the Nebius key, verify the adapter end-to-end, freeze feature work |
| **2** | README + architecture diagram + copy result artifacts into the repo |
| **3** | record the demo (3 takes), capture screenshots |
| **4** | edit video, trim HACKATHON.md, final repo cleanup |
| **5** | submit + buffer for upload problems |

## 7. Risks

| risk | mitigation |
|---|---|
| no Nebius key â†’ sponsor angle collapses | **blocking**: get it today; the adapter is ready |
| demo machine is slow / drive flaky | pre-record; keep the repo on `C:` and push to GitHub |
| judge asks "is this a real ASIC?" | say plainly: iCE40 FPGA P&R with real timing; ASIC mapping is future work |
| judge asks about the 33 failures | show the failure taxonomy (behaviour mismatch, not synthesizable) â€” it proves the gate works |
| D: drive drops (already happening) | never store the only copy there; push everything to GitHub |

## 8. What we will not claim

- Not a full ASIC flow (iCE40 FPGA place-and-route is real, ASIC is next).
- Not 50/50: **36/50**, stated up front.
- Not GPU-native locally: the GPU story is Nebius-hosted inference.

---

## 9. The one sentence to end the video on

> "Anyone can make a model write Verilog. Coal makes it prove the chip works â€”
> or refuses to call it a chip."
