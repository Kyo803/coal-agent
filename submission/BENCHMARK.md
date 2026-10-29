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
