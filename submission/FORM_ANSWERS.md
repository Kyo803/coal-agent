# Answers for the submission form

Every number here is reproducible with the scripts in `lm_track/coal_chat/`.
Where a measurement is noisy, it says so.

## Which model(s) did you use, and why that size?

**`nvidia/nemotron-3-super-120b-a12b`** on Nebius Token Factory.

It is a 120B sparse mixture-of-experts with **12B active parameters per
token**. That is the sweet spot for this workload:

- **Big enough for RTL.** Verilog is a low-resource language; small models
  produce plausible-looking code with wrong bit widths and wrong clocking. The
  120B variant got the interface and structure right far more often than the
  local 7B.
- **Cheap and fast enough to iterate.** Because only 12B parameters are active
  per token, it is a fraction of the cost and latency of a dense model of
  similar quality (`Nemotron-3-Ultra-550b-a55b` is available on the same
  account and was left for hard cases).
- **Reasoning works against us here.** Nemotron-3 is a reasoning model. Left
  on, it spent the whole token budget on its hidden trace and returned **zero
  bytes of Verilog**. We run it with `reasoning_effort: none` so the budget
  goes to code. The trust in this system comes from the verification gate, not
  from the model's chain of thought.

## Rate Nemotron's output quality (1–10)

**6 / 10.**

Measured, not asserted. Three batteries, all with the model writing RTL only
against an independent reference-model testbench:

| battery | result |
|---|---|
| 6 novel **combinational** designs | **6 / 6, all first try** |
| 4 **sequential** designs with crisp specs | **3 / 4** (3 first try) |
| 10 catalogue designs (terse specs, complex) — one-shot | **2 / 10** |
| same, with up to 2 repairs | **5 / 10** |

The spread is the honest characterisation, and it points at the real variable:
**specification quality.** With a precise interface contract the model passes
sequential designs 3/4 first try; with the catalogue's one-line bench specs it
passes 2/10. The repair loop closes much of that gap.

Why 6 and not lower: the failures are *ordinary* and *fixable* — a duplicate
signal declaration, a wrong LFSR polynomial, a signed right-shift it got
backwards, an overlapping sequence detector that never distinguished restart
from continuation. It is not producing nonsense; it is producing code that is
wrong in ways a real toolchain catches.

Why not higher: even on well-specified designs it is 3/4, not 4/4, and a
toolchain is the only reason you would trust any of it.

## Fine-tune, prompt-engineer, or out of the box?

**Out of the box — no fine-tuning.**

Prompt engineering only: the model is given the specification, the exact port
list, and a strict "return only the Verilog module" instruction. The design of
the system does the rest:

- the model never writes the testbench,
- the testbench is generated from a **separate Python model of the
  specification**,
- the design is accepted only if lint, simulation, synthesis, formal and
  place-and-route all pass.

The repair loop feeds the gate's own error text back to the model, so the
feedback the model learns from is the real toolchain's, not a prompt's opinion.

## How did it compare to other models?

Same ten designs, same specification, same ports, same independent
reference-model testbench, same gate.

| model | one-shot | with repair |
|---|---|---|
| `nvidia/nemotron-3-super-120b-a12b` (Token Factory) | 2 / 10 | **5 / 10** |
| `qwen2.5-coder:7b` (local, CPU) | 3 / 10 | 3 / 10 |

The comparison is fair in the way that matters: neither model ever sees the
testbench, and neither is graded by anything it wrote.

**The interesting difference is not the raw score — it is what happens when the
gate talks back.** The 7B gained nothing from error feedback (3 → 3). Nemotron
gained three designs (2 → 5). Being able to read a real toolchain's error and
act on it is a distinct capability, and it is the one this system depends on.

Caveat, stated plainly: ten designs, single samples, and the models are
stochastic even at `temperature = 0.15`. Treat this as directional, not
statistically settled.

## Which Nebius capabilities were most valuable?

**Token Factory hosted inference.** Specifically:

- **It removed the hardware ceiling.** The design step is the only part that
  needs a large model. Locally that meant an 8 GB-class GPU or a CPU at roughly
  20 tokens/second, which made iterating on 50 designs impractical. Token
  Factory put the design step on NVIDIA GPUs while verification stayed local.
- **The OpenAI-compatible API meant the integration was a drop-in.** The same
  adapter points at an NVIDIA NIM endpoint by changing one environment
  variable (`CoalEBIUS_URL`), so there is no vendor lock-in in the code.
- **Per-token billing matched the workload.** Verification is deterministic and
  free; only the design step costs anything, and it is bursty.

## How was the project significantly updated with Nebius tools?

Coal already had the verification engine: the gate, the reference-model
testbenches, the deterministic block library, the FPGA place-and-route. The
Nebius work is what made the **design** step viable at scale:

1. Replaced the local 7B design path with Nemotron-3 on Token Factory.
2. Added a provider-switchable adapter (`chipflow/model.py`) that speaks the
   OpenAI-compatible API, so Nebius, NVIDIA NIM and local Ollama are one
   environment variable apart.
3. Discovered and fixed a real integration failure: Nemotron-3's reasoning
   trace consuming the whole token budget and returning empty content. Fixed
   with `reasoning_effort: none`.
4. Built two benchmarks (`nemotron_bench.py`, `nemotron_rtl_bench.py`) that
   measure the model through the real gate rather than by inspection.

The result is measurable: the catalogue went from **36 / 50 to 44 / 50**
verified designs, with the eight new ones added as deterministic generator
blocks whose correctness is proven by independent reference models.
