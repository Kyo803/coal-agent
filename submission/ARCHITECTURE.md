# Architecture — why the result can be trusted

The whole design answers one question: **what makes an AI-authored chip
believable?**

The answer is not a better prompt. It is that the two things being compared —
the design and the expectation — are produced by different means.

```
             ┌──────────────────────┐
  spec  ────▶│  LLM (Nebius/NIM)    │──▶ block graph / RTL draft
             └──────────────────────┘
                        │
                        ▼
             ┌──────────────────────┐
             │  generator library   │──▶ RTL (Verilog-2001)
             └──────────────────────┘
                        │
  spec  ────▶┌──────────────────────┐
             │  Python model of the │──▶ stimulus ──▶ expected outputs
             │  specification       │
             └──────────────────────┘
                        │
                        ▼
             ┌──────────────────────┐
             │ refsim: emit TB      │──▶ testbench (generated)
             └──────────────────────┘
                        │
        RTL + TB ───────▼
             ┌──────────────────────┐
             │   verification gate  │
             │ lint · sim · synth · │
             │ formal · place&route │
             └──────────────────────┘
                        │
                        ▼
              verified chip + numbers
```

## 1. Two implementations of one specification

A block ships **RTL** and a **Python model**. They are written separately.
`refsim.build_tb()` walks the model over a stimulus schedule, records every
input/expected-output pair, and emits a Verilog testbench that replays the
same schedule against the DUT and compares every output, every cycle.

```python
def parity8():
    rtl = "module parity8 (...); assign err = (^data) ^ odd; endmodule"

    class M:                      # the specification, in Python
        def step(self, i):
            p = bin(i["data"]).count("1") & 1
            return {"err": p ^ (i["odd"] & 1)}

    stim = [{"data": d, "odd": o} for d in range(256) for o in (0, 1)]
    return _build("parity8", rtl, M(), stim, clocked=False)
```

The testbench is a *build artifact*. It cannot be hand-tuned to make a broken
design pass.

## 2. The gate

| stage | tool | what a failure means |
|---|---|---|
| lint | yosys `check -assert`, verilator `-Wall`, iverilog `-Wall` | the RTL is not valid or not structurally sound |
| sim | iverilog + vvp | the RTL disagrees with the specification |
| synth | yosys `synth` + ABC | it is not synthesizable (or collapses to nothing) |
| formal | yosys `check -assert` | latches, combinational loops |
| pnr | `synth_ice40` + `nextpnr-ice40` | it does not fit, or it misses timing |

Place-and-route reports `LC`, `IO`, achieved **Fmax**, `timing_met` and the
critical path. Combinational blocks route fine and report timing as `n/a`.

## 3. Composition

Multi-block chips are wired from blocks with a validated graph:

- every endpoint must be a real port
- widths must match exactly — no silent truncation
- exactly one driver per net, every input driven
- one clock/reset domain

Then the composed top goes through the same gate, with a **system testbench**
that proves the whole chip (`uart_loopback`: a byte sent on `serial_in` comes
back on `serial_out`).

## 4. Where the model is allowed to act

| task | model | guard |
|---|---|---|
| pick a block graph | yes | validated against real ports/widths; repaired at most twice |
| write a block's RTL | **no** | blocks come from the generator library |
| write a testbench | **no** | generated from the reference model |
| explain results | yes | no authority over the gate |

When a spec has no generator, the model *is* asked for RTL — and then it must
still pass the gate with an independently written testbench. Most fail. That
failure is reported, not hidden.

## 5. Adding a block

One function. No model involved.

```python
def lzc():
    rtl = """..."""                      # the design
    class M:                             # the specification
        def reset(self): pass
        def step(self, i):
            a = i["a"] & 0xFF
            return {"cnt": 8 - a.bit_length() if a else 8,
                    "allzero": 0 if a else 1}
    stim = [{"a": a} for a in range(256)]
    return _build("lzc", rtl, M(), stim, clocked=False)
```

The testbench is generated. Coverage grows one safe block at a time.

## 6. Failure taxonomy (why a chip is rejected)

- **behaviour mismatch** — RTL and reference model disagree (the useful signal)
- **not synthesizable** — logic optimised away, or unsupported constructs
- **lint/parse** — invalid Verilog (fences, SystemVerilog, mismatched width)
- **timing** — placed and routed but missed the target frequency
  (`COAL_PNR_STRICT=1` makes this a hard failure)

## 7. Non-goals

- Not an ASIC flow (iCE40 FPGA only, for now).
- Not a general-purpose HDL synthesiser.
- Not a claim that the LLM is good at Verilog — the claim is that its output
  is *checked*.
