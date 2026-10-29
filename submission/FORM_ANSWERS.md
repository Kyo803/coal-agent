# Answers for the submission form

Every number here is reproducible with the scripts in `lm_track/rox_chat/`.
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

Measured, not asserted. Ten catalogue designs, specification plus exact port
list, the model writes the RTL only, and the testbench comes from an
independently written Python reference model:

| measurement | result |
|---|---|
| one-shot, no repair | **2 / 10** pass the full gate |
| up to 2 repairs (model shown the gate's error text) | **5 / 10** pass the full gate |

Why 6 and not lower: the failures are *ordinary* and *fixable* — a duplicate
signal declaration, a wrong LFSR polynomial, a signed right-shift it got
backwards. It is not producing nonsense; it is producing code that is wrong in
ways a real toolchain catches. And it is genuinely better than the 7B.

Why not higher: a 50% pass rate on designs it has not seen is not a chip
designer. It is a fast first draft.

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
| `nvidia/nemotron-3-super-120b-a12b` (Token Factory) | 2 / 10 | 5 / 10 |
| `qwen2.5-coder:7b` (local, CPU) | *(see run)* | *(see run)* |

The comparison is fair in the way that matters: neither model ever sees the
testbench, and neither is graded by anything it wrote.

## Which Nebius capabilities were most valuable?

**Token Factory hosted inference.** Specifically:

- **It removed the hardware ceiling.** The design step is the only part that
  needs a large model. Locally that meant an 8 GB-class GPU or a CPU at roughly
  20 tokens/second, which made iterating on 50 designs impractical. Token
  Factory put the design step on NVIDIA GPUs while verification stayed local.
- **The OpenAI-compatible API meant the integration was a drop-in.** The same
  adapter points at an NVIDIA NIM endpoint by changing one environment
  variable (`ROX_NEBIUS_URL`), so there is no vendor lock-in in the code.
- **Per-token billing matched the workload.** Verification is deterministic and
  free; only the design step costs anything, and it is bursty.

## How was the project significantly updated with Nebius tools?

ROX N already had the verification engine: the gate, the reference-model
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
