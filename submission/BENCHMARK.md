# Nemotron benchmarks — two measurements that say different things

Both use the same gate: lint → simulation (iverilog) → synthesis (yosys + ABC)
→ formal → place & route (nextpnr-ice40). A design passes only if all five do.

**Model:** `nvidia/nemotron-3-super-120b-a12b` via Nebius Token Factory
(`https://api.studio.nebius.com/v1`), out of the box, no fine-tuning,
reasoning trace disabled (`reasoning_effort: none`).

---

## Benchmark 1 — model writes RTL *and* testbench

The naive setup, and what most "AI writes Verilog" demos actually do.

**Result: 0 / 6** of the designs the local 7B also failed.

But the breakdown matters more than the number:

| design | failed stage | cause |
|---|---|---|
| `elevator` | sim | genuine behaviour mismatch |
| `sar_adc` | sim | genuine behaviour mismatch |
| `keypad` | sim | testbench elaboration error |
| `melody` | sim | testbench syntax error |
| `spi_slave` | sim | testbench elaboration error |
| `spi_master` | sim | testbench redeclaration error |

**Synthesis, formal and place-and-route passed for all six.** Four of the six
failures were the model failing to write a *compiling testbench* — not the RTL
being wrong.

That is the project's thesis in one table: when the same process writes the
design and the test, the failure tells you almost nothing about the design.

---

## Benchmark 2 — model writes RTL only, independent testbench

This isolates RTL quality the way the system is actually built.

- the model gets the specification and the **exact port list**
- it writes **only** the Verilog
- the testbench comes from the block's **independent Python reference model**
- the same five-stage gate decides pass/fail

### One-shot (no repair)

**2 / 10** passed. Failures were real RTL bugs: a duplicate signal declaration,
a wrong LFSR polynomial, inverted edge logic, a parity convention mismatch.

### With up to 2 repairs

The model is shown the gate's own error text and asked to fix its RTL.

**5 / 10** passed.

| design | one-shot | with repair | repairs used | failure when it failed |
|---|---|---|---|---|
| `parity` | — | PASS | 0 | |
| `popcount` | — | PASS | 0 | |
| `bitrev` | FAIL | FAIL | 2 | output stayed `00000000` |
| `edge_detect` | — | PASS | 0 | |
| `lfsr8` | FAIL | FAIL | 2 | wrong polynomial / shift direction |
| `prio16` | FAIL | FAIL | 2 | yosys parse error |
| `satadd` | PASS | PASS | 0 | |
| `hamming_enc` | PASS | FAIL | 2 | wrong parity-bit placement |
| `seqdet` | FAIL | FAIL | 2 | overlapping-detect logic wrong |
| `barrelshift` | FAIL | PASS | 1 | signed right-shift mode |

> The one-shot and repair runs are separate samples, and the model is
> stochastic even at `temperature = 0.15`. `parity`, `popcount`,
> `hamming_enc` and `edge_detect` flipped between runs. Treat these as
> single-sample estimates, not stable scores.

---

## Benchmark 3 — head to head, same ten designs

Identical specification, identical port list, identical independent
reference-model testbench, identical gate. Neither model ever sees the test.

| model | one-shot | with up to 2 repairs | gained from repair |
|---|---|---|---|
| `nvidia/nemotron-3-super-120b-a12b` (Token Factory) | 2 / 10 | **5 / 10** | **+3** |
| `qwen2.5-coder:7b` (local, CPU) | 3 / 10 | 3 / 10 | +0 |

The raw one-shot scores are comparable. **The difference is what each model
does when the gate tells it what went wrong.** The 7B could not convert error
feedback into fixes; Nemotron converted three failures into passes.

That is the capability this architecture is built to exploit: the gate is not
just a filter, it is a feedback channel.

Raw report: `~/.rox/work/nemotron_rtl/QWEN_7B_RTL.md`.

---

## Benchmark 4 — six novel designs (not in the catalogue)

To check the model is not just memorising the catalogue, six designs that are
not in it at all were run the same way: spec + exact ports, RTL only,
independent reference-model testbench, full gate.

**6 / 6 passed, every one first try, zero repairs.**

| design | what it does | result |
|---|---|---|
| `bin2gray4` | 4-bit binary to Gray | PASS, 0 repairs |
| `popcount6` | count 1 bits in 6 bits | PASS, 0 repairs |
| `min3_4bit` | minimum of three 4-bit values | PASS, 0 repairs |
| `majority3` | 3-input majority voter | PASS, 0 repairs |
| `thermometer3to7` | 3-to-7 thermometer decode | PASS, 0 repairs |
| `palindrome8` | 8-bit bit-palindrome detector | PASS, 0 repairs |

These six are combinational. The ten in benchmarks 2–3 are sequential and
harder, which is where the 2–5/10 comes from. Stated together so the contrast
is not hidden: **Nemotron is reliable on straightforward combinational logic
and still error-prone on stateful designs.**

One fix made the difference on first-try passes: the system prompt now
requires ANSI-style ports (`output reg [3:0] b` inline) instead of declaring
the output and a separate `reg` with the same name, which the model kept doing
and which is a compile error.

Reproduce: `py -3.15 test_nemotron_novel.py` (needs `NEBIUS_API_KEY`).

---

## Benchmark 5 — sequential designs

Six combinational wins could mean the model only handles easy wiring. Four
**clocked, stateful** designs were run the same way (spec + ports, RTL only,
independent reference-model testbench, full gate):

| design | result |
|---|---|
| `upcounter4` — 4-bit counter, enable | **PASS**, 0 repairs |
| `shiftreg4` — serial-in parallel-out shift register | **PASS**, 0 repairs |
| `pulse_detect` — one-cycle rising-edge pulse | **PASS**, 0 repairs |
| `seqdet101` — overlapping 101 detector | **FAIL** (2 repairs, stayed wrong) |

**3 / 4**, all three passes first try.

`seqdet101` is the honest failure: overlapping sequence detection needs the
state machine to distinguish "101 then a new 1" from "restart", and the model
never got it right. That is a real RTL bug, not a harness artefact.

### So why is the catalogue only 2–5 / 10?

The catalogue designs are harder in a specific way: their specifications are
terse one-liners written for a bench, not precise interface contracts, and
several combine generation and timing concerns. The bench designs above had
crisp specifications.

That is the useful conclusion, and it is actionable: **the model's ceiling
depends heavily on specification quality.** A precise spec moved sequential
pass rates from roughly 2/10 to 3/4 on these samples.

Reproduce: `py -3.15 test_nemotron_seq.py` (needs `NEBIUS_API_KEY`).

---

## What this is evidence for

The architecture is not "the model is good". It is **"the model proposes, the
tools decide"**.

Benchmark 1 shows the model cannot police itself: given both jobs, it wrote
four non-compiling testbenches in six designs. Benchmark 2 shows that the same
model, checked against an independent oracle, is held to a standard it cannot
talk its way past — and that every failure is attributable to the RTL, which
is what makes the repair loop meaningful.

Reproduce:

```powershell
$env:NEBIUS_API_KEY = "..."
py -3.15 nemotron_bench.py                        # benchmark 1
py -3.15 nemotron_rtl_bench.py                    # benchmark 2, one-shot
py -3.15 nemotron_rtl_bench.py --repairs 2        # benchmark 2, with repair
```

Raw outputs: `~/.rox/work/nemotron_bench/` and `~/.rox/work/nemotron_rtl/`.
