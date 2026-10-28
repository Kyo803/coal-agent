# 08 — Training Track (from-scratch 500M/1B)

## Purpose

This is the *other* half of ROX N: an attempt to build a chat model
**from scratch** on the user's own machine, using custom architectures.
It is experimental and separate from the shipped 35B runtime.

> **Status (honest):** The 35B is the production brain. The training
> track produced small checkpoints (500M-1B) that reach SFT/DPO stage
> but are far below the 35B's conversational quality. The architecture
> work is real and documented; the models are research artifacts, not
> the assistant.

## The architecture (`arch.py`, `arch_v2.py`)

`RoxChat` — a custom transformer fusing "surprise-gated" mechanisms:
- **FOU** (First-Order Uncertainty) — dense FFN + sparsity aux loss
  (train) / hard top-k surprise caches (infer)
- **EME** (Expert-MoE routing) — top-2 gating + load balance (train) /
  hysteresis (infer)
- **PLHE** — preference/history mechanisms
- EME-routed MoE on `moe_every` layers, dense SwiGLU elsewhere
- Two execution modes (parallel-train vs streaming-infer) bridged by a
  **Stage-0 parity gate** (`stage0.py`, `stage0.json`)

Deliberately excludes `rox_m` emotion mechanisms (never trained, per
audit).

## The data factory

| Script | Purpose |
|---|---|
| `tokenizer_train.py` / `tokenize_corpus.py` | custom BPE tokenizer |
| `datamix_convo.py` | conversational-first mix (14.2B dialogue over 39.4B foundation, 60B total) |
| `datamix_60B.py` | web-volume fallback mix |
| `sft_data.py` / `datamix_v2.py` / `instruction_augment.py` | SFT data |
| `fetch_code.py` / `fetch_convo.py` | dataset fetching |
| `safety_data.py` / `atp_data.py` | safety alignment data |

## Training pipeline

| Stage | Script | Checkpoints |
|---|---|---|
| Pretrain | `train_500m.py --mode pretrain` | `rox_500m/pretrain.pt` |
| SFT | `train_500m.py --mode sft` | `rox_500m/sft.pt` |
| Alignment | `train_500m.py --mode align` | `rox_500m/align.pt` |
| 1B scale | `train_v2.py`, `arch_v2.py` | `rox_brain/` |
| LoRA SFT | `train_sft.py`, `sft_v2.py` | LoRA-0.46M on 20K pairs |
| DPO | `train_dpo.py`, `run_online_dpo.py`, `run_kto.py`, `run_orpo.py`, `run_grpo.py` | `rox_dpo/`, `rox_kto/`, `rox_orpo/`, `rox_online_dpo/` |
| Distill | `run_distill.py`, `run_grpo.py` | from larger checkpoints |
| Merge/quant | `merge_now.py`, `quantize.py`, `pack_shards.py` | GGUF? (for the 35B this is external) |

Optimizers/techniques: `muon.py`, `lora.py`, `mopd.py`,
`lambda_governor.py`, `parity.py`, `calibrate.py`.

## Key results (documented in `PLAN_500M_1B.md`)

- **SFT status: COMPLETE** — 1000/1000, val 2.576, `rox_brain/` live.
  LoRA-0.46M on 20K dialogue pairs. Resumed from checkpoints twice
  (25-step chain held). 36-QA: base 0.61 / ours 0.50 (SFT factuality
  tax); identity fixed (Rox, not SmolLM).
- **Next (documented):** DPO identity/grounding repair, rental-scale run.
- **A-60B rental package**: `datamix_convo.py`, 12.6h wall on 10×A-H100
  @40% MFU, ~$487 clean; all-in $600-800. Architecture + Stage-0 PASS
  on file. GPU stages are resourcing, not research.

## Why the 35B is the production brain

The 500M/1B checkpoints cannot hold a real conversation as well as the
35B. The runtime was therefore built around the 35B, and the training
track remains a research line. The eval report's honest conclusion: the
135M model scored ~49% QA / ~28% multi-turn; the 35B raises both to
100% — proving the gap was model capacity, not the system.

## Operational notes

- `train_all.ps1`, `train_ddp.py`, `pretrain_watch.ps1`,
  `dpo_watch.ps1`, `overnight.ps1` — batch/resume/GPU-launch helpers
- Checkpoint files (`ckpt_*.pt`) are large (2.8 GB each) — do not commit
- Logs (`train_log.txt`, `pretrain_log.txt`, `overnight.log`, `dpo_*.log`)
  are diagnostic