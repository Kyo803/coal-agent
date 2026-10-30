# 07 — TRAINING PIPELINE AUDIT (training, data, models, GPU)

The research/training track that produced the brains and the plan for bigger
ones. Everything is **CPU-verified and staged**; nothing has been run on rented
GPUs yet (see `gpu/RUNBOOK.md`). This document lists every file in that track.

---

## 1. Architecture / config / gates

| File | Purpose |
|------|---------|
| `arch.py` (15.4 KB) | Coal-Chat unified architecture (500M/1B track): layer/width/MoE configs, verified programmatically (not by hand). |
| `arch_v2.py` (16.5 KB) | V2 architecture: modern small-MoE recipe + the Coal mechanisms (PLHE/FOU/EME). |
| `verify_arch.py` (4.7 KB) | Phase-A gate: architecture v2 must pass before any training code. |
| `config_v2.py` (3.4 KB) | V2 configs: model tiers + training recipe + data mix. |
| `stage0.py` (3.2 KB) | Stage-0: prove PLHE/FOU/EME compose and train stably at tiny scale. `stage0.json` = results (PASS). |
| `stage0.json` | Stage-0 run history (loss, val, min_expert per step). |

## 2. Optimizers / mechanisms (research inventions, all CPU-verified)

| File | Purpose |
|------|---------|
| `muon.py` (5.4 KB) | Muon optimizer (Liu et al. 2025) + AdamW hybrid. |
| `lambda_governor.py` (3.1 KB) | Lambda Governor: closed-loop EME hysteresis control (MoE-collapse escape). Proven by ablation. |
| `matrix.py` (3.5 KB) | Interaction-matrix runner: pairwise mechanism ablation at small scale. `matrix.json` = results (balance-aux is load-bearing). |
| `fim.py` (6 KB) | FIM — Fast Interaction Matrix via gradient-conflict screening. `fim.json` = conflict scores. Offline only. |
| `parity.py` (3 KB) | Parity Sentinel: keeps FOU training approximation honest vs inference. |
| `calibrate.py` (2 KB) | STR Calibrator: freeze retrieval thresholds per model scale → `str_config.json`. |
| `latency.py` (2.3 KB) | Latency Accountant: per-token stage budget with shedding. |
| `rental_guardian.py` (3.3 KB) | Rental Guardian: preflight gates + in-run watchdog for rented GPUs. |
| `mopd.py` (5.4 KB) | MOPD — Multi-Teacher On-Policy Distillation. |
| `lora.py` (2.9 KB) | Manual LoRA (no peft): low-rank adapters on q/v projections. |

## 3. Data pipeline

| File | Purpose |
|------|---------|
| `datamix_convo.py` (3.7 KB) | **Conversational-first 60B manifest** (the PRIMARY data plan): 14.2B dialogue/instruction tokens oversampled over 39.4B English foundation. |
| `datamix_60B.py` (2 KB) | Fallback web-volume 60B manifest (same target). |
| `datamix_v2.py` (3.1 KB) | Compute the 100B code-first data manifest from staged + fetched sources. |
| `fetch_convo.py` (7.2 KB) | Fetch fresh conversational + English-teaching data (local staging) → `data_fresh/`. |
| `fetch_code.py` (4.1 KB) | Fetch code + math corpora for the 100B code-first mix. |
| `sft_data.py` (4.2 KB) | SFT pairs mined from OUR staged dialogue (`data_fresh`), not hand-written. |
| `sft_train.jsonl` (9.3 MB) | The SFT training set (mined dialogue pairs). |
| `sft_val.jsonl` (0.5 MB) | The SFT validation set. |
| `dpo_prefs.jsonl` (119.6 MB) | DPO preference data. |
| `persona_prefs.json` | Identity/grounding preference pairs (Coal vs roleplay residue). |
| `safety_data.py` (5.7 KB) | Safety training data: replaces the hardcoded crisis list with learned examples. |
| `atp_data.py` (4.3 KB) | ATP data: Adversarial-Training / pushback pairs. |
| `instruction_augment.py` (4.5 KB) | Instruction pre-training augmentation (InstructLM-style). |
| `tokenize_corpus.py` (5 KB) | Tokenize staged corpora to uint16 shards per the data manifest. |
| `tokenizer_train.py` (3.3 KB) | Train a from-scratch byte-level BPE tokenizer (vocab 50,304) on our corpora. |
| `bpe.py` (2.2 KB) | Minimal byte-level BPE (32K target; tiny demo). `bpe_demo.json` = demo merges. |
| `pack_shards.py` (2.7 KB) | Validate tokenized shards + provide the memmap loader used by training. |

## 4. Training entry points

| File | Purpose |
|------|---------|
| `train_500m.py` (11.8 KB) | 500M from-scratch pretrain + SFT + alignment on CPU (resumable). |
| `train_ddp.py` (3.7 KB) | Rental entry: torchrun DDP/FSDP pretraining for CoalChat-500M on 60B. |
| `train_v2.py` (6.7 KB) | V2 trainer: WSD schedule + Muon + two-phase context + FP8/BF16. |
| `train_sft.py` (6 KB) | SFT on OUR dialogue (`sft_train.jsonl`): LoRA q/v, assistant-masked loss. |
| `train_dpo.py` (5.9 KB) | DPO alignment on prefs + persona set. |
| `sft.py` (1.3 KB) | Masked SFT: loss on assistant tokens only. Generic over any model. |
| `sft_v2.py` (7.5 KB) | SFT v2: instruction + conversation + memory-tools + safety + code. |
| `dpo.py` (1.7 KB) | DPO alignment pass (cheapest preference method): pushback + persona. |
| `run_distill.py` (4.3 KB) | Self-distillation save-point: SFT on own best rollouts. |
| `run_grpo.py` (5.1 KB) | GRPO (Group Relative Policy Optimization) — DeepSeek's method. |
| `run_kto.py` (4 KB) | KTO (Kahneman-Tversky Optimization) — unpaired thumbs up/down. |
| `run_online_dpo.py` (5 KB) | Online Iterative DPO: generate → rank → train → repeat. |
| `run_orpo.py` (3.3 KB) | ORPO (Odds Ratio Preference Optimization) — SFT + alignment in one loss. |
| `align_v2.py` (7 KB) | Unified alignment: DPO / KTO / ORPO / GRPO in one script. |
| `merge_now.py` (1.4 KB) | Merge LoRA adapters from `ckpt_sft.pt` into base → save `coal_brain/`. |
| `quantize.py` (2.8 KB) | Weight-only int8/int4 quantization for local deployment. |
| `sentinel_hooks.py` (2 KB) | Wire the risk-invention safeguards (governor, parity, balance-bias) into the v2 training loop. |

## 5. GPU staging (`gpu/`)

| File | Purpose |
|------|---------|
| `gpu/RUNBOOK.md` (3.3 KB) | **The rental runbook** (10× H200, ~$55–85): exact staged sequence, costs, resume, safeguards, honest expectations. Read this before any GPU work. |
| `gpu/preflight.py` (3.1 KB) | GPU preflight: fail fast BEFORE burning rental time. |
| `gpu/stage1_fetch.sh` | Fetch + tokenize. |
| `gpu/stage2_pretrain.sh` | Pretrain 500M/1B. |
| `gpu/stage3_sft.sh` | SFT. |
| `gpu/stage4_align.sh` | Alignment (DPO/KTO/ORPO/MOPD). |
| `gpu/stage5_eval.sh` | Eval + export (int8/int4). |

## 6. Model weights / tokenizers / checkpoints (data, not source)

| Path | Contents |
|------|----------|
| `coal_brain/chat_template.jinja`, `coal_brain/config.json`, `coal_brain/generation_config.json`, `coal_brain/model.safetensors` (282 MB), `coal_brain/tokenizer.json`, `coal_brain/tokenizer_config.json` | SFT brain (135M-class) — the chat model SFT output. |
| `coal_chat/chat_template.jinja`, `coal_chat/config.json`, `coal_chat/generation_config.json`, `coal_chat/model.safetensors`, `coal_chat/tokenizer.json`, `coal_chat/tokenizer_config.json` | Another SFT snapshot, same HF layout. |
| `coal_kto/chat_template.jinja`, `coal_kto/config.json`, `coal_kto/generation_config.json`, `coal_kto/model.safetensors`, `coal_kto/tokenizer.json`, `coal_kto/tokenizer_config.json` | KTO alignment checkpoint. |
| `coal_online_dpo/chat_template.jinja`, `coal_online_dpo/config.json`, `coal_online_dpo/generation_config.json`, `coal_online_dpo/model.safetensors`, `coal_online_dpo/tokenizer.json`, `coal_online_dpo/tokenizer_config.json` | Online-DPO alignment checkpoint. |
| `coal_orpo/chat_template.jinja`, `coal_orpo/config.json`, `coal_orpo/generation_config.json`, `coal_orpo/model.safetensors`, `coal_orpo/tokenizer.json`, `coal_orpo/tokenizer_config.json` | ORPO alignment checkpoint. |
| `coal_500m/pretrain.pt`, `coal_500m/sft.pt`, `coal_500m/align.pt` | 500M-track checkpoints (~5.66 GB each). |
| `ckpt_sft.pt`, `ckpt_dpo.pt`, `ckpt_kto.pt` | Raw training checkpoints (LoRA / full) used by `merge_now.py` and comparison scripts. |
| `tokenizer_v2/vocab.json`, `tokenizer_v2/merges.txt`, `tokenizer_v2/report.json` | The 50,304-vocab BPE tokenizer + roundtrip report. |
| `bigindex/passages.jsonl`, `bigindex/index.pkl` | Corpus retrieval index (see `03-…`). |

## 7. Plans / docs in the training track

| File | Purpose |
|------|---------|
| `PLAN_500M_1B.md` | The 500M/1B build plan: costed tokens, stages, mechanism → "fewer side effects" mapping, what stays OUT. |
| `LOCAL_RUN.md` | Local run guide (talk to Coal, backends, speed tips). |
| `gpu/RUNBOOK.md` | Rental runbook (see above). |

---

_Next: `08-CONFIG-DATA-ARTIFACTS.md`._