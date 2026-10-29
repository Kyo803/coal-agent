# Nemotron RTL-only benchmark (independent reference-model TB)

- model    : `nvidia/nemotron-3-super-120b-a12b`
- endpoint : `https://api.studio.nebius.com/v1`
- method   : model writes RTL from spec + exact ports; the testbench
             comes from the block's independent Python reference model
- repairs  : 2 (model sees the gate's error text and retries)
- result   : **5/10 passed the full gate**

| design | result | time | repairs | cells/FF | Fmax | failure |
|---|---|---|---|---|---|---|
| `parity` | PASS | 8.9s | 0 | -/- | - | - |
| `popcount` | PASS | 5.0s | 0 | -/- | - | - |
| `bitrev` | FAIL | 8.2s | 2 | -/- | - | sim: bitrev8:FAIL vec=262 y=00000000 bitrev8:FAIL vec=263 y=00000000 bitrev8:FAIL vec=266 y=00000000 bitr |
| `edge_detect` | PASS | 3.1s | 0 | -/- | - | - |
| `lfsr8` | FAIL | 5.1s | 2 | -/- | - | sim: lfsr8:FAIL vec=68 q=00000011 lfsr8:FAIL vec=69 q=00000110 lfsr8:FAIL vec=70 q=00000110 lfsr8:FAIL ve |
| `prio16` | FAIL | 2.0s | 2 | -/- | - | lint: [yosys] | | Copyright (C) 2012 - 2020 |
| `satadd` | PASS | 1.9s | 0 | -/- | - | - |
| `hamming_enc` | FAIL | 2.8s | 2 | -/- | - | sim: hamming_enc:FAIL vec=1 code=0101001 hamming_enc:FAIL vec=2 code=1001010 hamming_enc:FAIL vec=3 code= |
| `seqdet` | FAIL | 3.4s | 2 | -/- | - | sim: seqdet:FAIL vec=2 found=1 seqdet:FAIL vec=3 found=0 seqdet:FAIL vec=5 found=1 seqdet:FAIL vec=6 foun |
| `barrelshift` | PASS | 3.7s | 1 | -/- | - | - |

## What this means

Nemotron's RTL passed **5/10** when checked against an independent reference model. The failures are real RTL bugs, not testbench artefacts -- the testbench was never written by the model.

This is the number to compare against other models: same spec, same ports, same reference-model testbench, same gate.
