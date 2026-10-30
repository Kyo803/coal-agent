# Coal-Chat 500M/1B build plan (chattable, hallucination-resistant)

## 0a. SFT status (COMPLETE): 1000/1000, val 2.576, coal_brain/ live

LoRA-0.46M on 20K dialogue pairs. Killed twice by machine load, resumed
from checkpoints both times (25-step chain held). Before/after on 36-QA:
base 0.61 / ours 0.50 (SFT factuality tax, modest), identity fixed (Coal,
not SmolLM). Chat auto-uses coal_brain. Next: DPO identity/grounding
repair (Alex-Jones-class roleplay residue) + rental-scale run.

## 0. 500M × 60B rental package (FIM offline, out of the hot loop)

PRIMARY: `datamix_convo.py` — conversational-first: 14.2B dialogue/
instruction tokens sampled at 0.56 weight (deliberate oversample) over
39.4B English-teaching foundation (FineWeb-Edu stream, books, clean EN);
1.12 epochs to 60B. Pure-60B-human-dialogue doesn't exist publicly —
categories are labeled for ablation.
Fallback: `datamix_60B.py` (web-volume mix, same 60B target).
Measured: **12.6h wall on 10×H100 @40% MFU, ~$487 clean**
(10.1h @50%, 15.3h @33%). All-in with SFT+DPO: **$600–800**.
FIM stays an offline analysis script — never in the training loop.

Status: architecture + Stage-0 PASS on file (`arch.py`, `stage0.py`,
`stage0.json`). GPU stages are resourcing, not research — every number
below is computed, not guessed.

## 1. Configs (verified by `arch.py`, not by hand)

| model | layers | width | MoE layers | experts (top-2) | total | active/tok |
|---|---|---|---|---|---|---|
| coal-chat-500M | 18 | 960 | every 4th (4) | 8 | **478M** | 234M (49%) |
| coal-chat-1B | 24 | 1216 | every 4th (6) | 8 | **1025M** | 508M (50%) |

Lesson from the 1.5B-plan audit: full-size experts on every layer
overshoots 4–7x. MoE every 4th layer is what makes these labels honest.

## 2. Costs (C=6ND, H100 @400 TFLOPs sustained, $3.85/hr on-demand)

| run | tokens | clean GPU-hrs | clean $ | all-in (1.5–3x) |
|---|---|---|---|---|
| 500M / 10B (Chinchilla) | 10B | ~21 | ~$80 | **$150–300** |
| 1B / 20B (Chinchilla) | 20B | ~83 | ~$320 | **$500–1,000** |
| SFT (896K pairs, both) | — | — | — | +$100–200 |
| DPO alignment | — | — | — | +$100–300 |

Single 8×H100 node, FSDP + expert parallelism (`llm_500m/configs/`
already has the FSDP/DeepSpeed configs). QMessage: the 500M full
pipeline fits under $500 all-in — that is the recommended first target.

## 3. Stages (mapped to existing repo assets)

0. **Stage-0 (DONE, CPU):** mechanisms compose, no collapse, PLHE kept.
1. **Tokenizer:** finish the 32K BPE in `llm_500m` (~1 day left per audit);
   4K convo tokenizer is English-only and too small for 500M.
2. **Pretrain 500M** on `data/corpus` (20.7GB) + multilingual top-up.
   Go/no-go: val loss on track + expert spread monitored from step 1.
3. **SFT** on the 896K mined pairs (`mine_sft.py` output, unused so far).
4. **DPO** on pushback/false-premise pairs (resilience ATP requirement);
   needs rater effort — synthetic prefs first, human pass second.
5. **Inference attachments** (no extra training): two-stage STR trigger
   (`lm_track/str_trigger/trigger_spec.md`, measured), TME turn memory,
   calculator/code tool gate, crisis lockout (already 11/11 recall).
6. **Eval gates before calling it chattable:** held-out factuality
   (STR on/off), MT-style multi-turn coherence with planted facts,
   adversarial instruction set, fallback drills (retrieval down, tool
   error). Same A/B protocol that caught the 35.7M model losing 100%.

## 4. How the custom mechanisms map to "fewer side effects"

| weakness | mechanism | honesty note |
|---|---|---|
| hallucination | two-stage STR (min-prob gate + consistency check) | measured 0.85 AUROC; S_t deliberately NOT the trigger (§spec) |
| confident fluent falsehoods | domain always-retrieve policy + ATP pushback data | no threshold catches these; policy + training do |
| multi-turn drift | TME (surprise-scored compression) | compression rule validated at signal level; needs long-dialog eval |
| MoE collapse/gibberish | EME hysteresis + balance aux loss + Stage-0 spread gate | hysteresis pulls toward stickiness — λ schedule is the knob |
| wasted edge compute | FOU inference caches + EME 1-expert echo | proven at signal scale (97%); LM-scale savings unproven until §2 runs |

## 6. Risk inventions (all built, all CPU-verified)

`lambda_governor.py` (collapse escape proven) · `parity.py` (drift
control loop) · distiller (`llm_500m/scripts/`, refused to corrupt:
PROBE_TOO_WEAK) · `matrix.py` (balance-aux proven load-bearing by
ablation) · `fallbacks.py` (§7 as code, 5 rows + drills) ·
`calibrate.py` (frozen θ1=0.49/dis=0.5 from measured data) ·
`rental_guardian.py` (preflight + $38.50/hr watchdog) · `latency.py`
(shedding accountant) · `scan_contamination.py` (0/36 quarantined).

## 7. What stays OUT (audit discipline)

coal_m emotion mechanisms (limbic routing, emotion RoPE, gradient decay
as run) — never trained per the audit; they re-enter only with their own
Stage-0 gates. The 2B stub stays a stub until 500M ships.
