# Nemotron RTL-only benchmark (independent reference-model TB)

- model    : `nvidia/nemotron-3-super-120b-a12b`
- endpoint : `https://api.studio.nebius.com/v1`
- method   : model writes RTL from spec + exact ports; the testbench
             comes from the block's independent Python reference model
- result   : **2/10 passed the full gate**

| design | result | time | cells/FF | Fmax | failure |
|---|---|---|---|---|---|
| `parity` | FAIL | 6.0s | -/- | - | sim: err=0
parity8:FAIL vec=404 err=1
parity8:FAIL vec=405 err=0
parity8:FAIL vec=406 err=0
parity8:FAIL  |
| `popcount` | FAIL | 3.6s | -/- | - | lint: [verilator] %Error: popcount4.v:5:15: Duplicate declaration of signal: 'cnt'
                        |
| `bitrev` | FAIL | 2.2s | -/- | - | sim: bitrev8:FAIL vec=262 y=00000000
bitrev8:FAIL vec=263 y=00000000
bitrev8:FAIL vec=266 y=00000000
bitr |
| `edge_detect` | FAIL | 2.7s | -/- | - | sim: vec=31 rising=0 falling=0 both=0
edge_detect:FAIL vec=34 rising=0 falling=0 both=0
edge_detect:FAIL  |
| `lfsr8` | FAIL | 11.1s | -/- | - | sim: r8:FAIL vec=43 q=10101010
lfsr8:FAIL vec=44 q=11010101
lfsr8:FAIL vec=45 q=11101010
lfsr8:FAIL vec=4 |
| `prio16` | FAIL | 5.5s | -/- | - | lint: [yosys]                                                          |
 |  Copyright (C) 2012 - 2020  Cl |
| `satadd` | PASS | 2.2s | -/- | - | - |
| `hamming_enc` | PASS | 4.0s | -/- | - | - |
| `seqdet` | FAIL | 3.4s | -/- | - | sim: seqdet:FAIL vec=2 found=1
seqdet:FAIL vec=3 found=0
seqdet:FAIL vec=5 found=1
seqdet:FAIL vec=6 foun |
| `barrelshift` | FAIL | 2.3s | -/- | - | sim: barrelshift:FAIL vec=17 y=00000010
barrelshift:FAIL vec=21 y=00000100
barrelshift:FAIL vec=25 y=0001 |

## What this means

Nemotron's RTL passed **2/10** when checked against an independent reference model. The failures are real RTL bugs, not testbench artefacts -- the testbench was never written by the model.

This is the number to compare against other models: same spec, same ports, same reference-model testbench, same gate.
