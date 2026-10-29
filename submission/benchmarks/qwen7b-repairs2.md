# Nemotron RTL-only benchmark (independent reference-model TB)

- model    : `qwen2.5-coder:7b`
- endpoint : `https://api.studio.nebius.com/v1`
- method   : model writes RTL from spec + exact ports; the testbench
             comes from the block's independent Python reference model
- repairs  : 2 (model sees the gate's error text and retries)
- result   : **3/10 passed the full gate**

| design | result | time | repairs | cells/FF | Fmax | failure |
|---|---|---|---|---|---|---|
| `parity` | PASS | 16.7s | 0 | -/- | - | - |
| `popcount` | PASS | 5.9s | 0 | -/- | - | - |
| `bitrev` | FAIL | 9.4s | 2 | -/- | - | sim: 11110111 bitrev8:FAIL vec=248 y=11111000 bitrev8:FAIL vec=249 y=11111001 bitrev8:FAIL vec=250 y=1111 |
| `edge_detect` | FAIL | 10.5s | 2 | -/- | - | sim: =0 falling=0 both=1 edge_detect:FAIL vec=58 rising=0 falling=1 both=0 edge_detect:FAIL vec=61 rising |
| `lfsr8` | FAIL | 13.7s | 2 | -/- | - | sim: lfsr8:FAIL vec=0 q=00000001 lfsr8:FAIL vec=1 q=00000010 lfsr8:FAIL vec=2 q=00000100 lfsr8:FAIL vec=3 |
| `prio16` | FAIL | 8.9s | 2 | -/- | - | lint: [yosys] | | Copyright (C) 2012 - 2020 |
| `satadd` | PASS | 9.1s | 0 | -/- | - | - |
| `hamming_enc` | FAIL | 12.7s | 2 | -/- | - | sim: hamming_enc:FAIL vec=1 code=0100101 hamming_enc:FAIL vec=2 code=1000110 hamming_enc:FAIL vec=3 code= |
| `seqdet` | FAIL | 13.3s | 2 | -/- | - | sim: seqdet:FAIL vec=4 found=1 seqdet:FAIL vec=5 found=1 seqdet:FAIL vec=7 found=1 seqdet:FAIL vec=8 foun |
| `barrelshift` | FAIL | 30.9s | 2 | -/- | - | lint: [iverilog] barrelshift.v:25: error: part select a[3:5] is out of order. barrelshift.v:26: error: par |

## What this means

Nemotron's RTL passed **3/10** when checked against an independent reference model. The failures are real RTL bugs, not testbench artefacts -- the testbench was never written by the model.

This is the number to compare against other models: same spec, same ports, same reference-model testbench, same gate.
