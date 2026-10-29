# Nemotron benchmark - the designs the local 7B could not build

- model           : `nvidia/nemotron-3-super-120b-a12b`
- endpoint        : `https://api.studio.nebius.com/v1`
- designs         : 6
- local 7B        : 0/6 passed
- Nemotron        : 0/6 passed

| design | category | local 7B | Nemotron | cells/FF | Fmax |
|---|---|---|---|---|---|
| `elevator` | control | FAIL | FAIL | 61/5 | 230.6 |
| `keypad` | input | FAIL | FAIL | 135/35 | 123.0 |
| `melody` | audio | FAIL | FAIL | 114/23 | 193.6 |
| `spi_slave` | peripheral | FAIL | FAIL | 27/21 | 302.9 |
| `spi_master` | peripheral | FAIL | FAIL | 102/24 | 201.9 |
| `sar_adc` | sensor | FAIL | FAIL | 78/23 | 222.3 |

## Answers to the submission questions

**Model used:** `nvidia/nemotron-3-super-120b-a12b`.

**Measured output quality:** 0/6 of the designs the 7B failed were built and passed the full gate (lint + simulation + synthesis + formal + place & route), versus 0/6 locally.

**How it was used:** out of the box - no fine-tuning. It is prompted to emit either a block graph or RTL, and its output is only accepted if an independently written Python reference model agrees with it cycle by cycle.

**Where Token Factory helped:** the design step is the only part that needs a large model. Hosted inference removed the 9 GB local RAM ceiling and the ~20 tok/s CPU bottleneck, so the whole design step runs on GPU while verification stays local and deterministic.
