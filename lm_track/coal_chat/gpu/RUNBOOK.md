# Coal — GPU Runbook (10× H200, ~$55–85)

Everything is built and CPU-verified. This is the exact sequence to run
on the rental. One command per stage; every stage is resumable.

## 0. Provision (once)

```bash
export COAL_DATA=/data/coal
export COAL_TOKENS_B=100
export COAL_TIER=500M
export COAL_FP8=1                 # FP8 (2x faster); unset for BF16
export CHECKPOINT_OFFLOAD=/data/coal/ckpt
export HF_TOKEN=hf_...           # for gated sets + rate limits

# clone/copy Coal to the node, then:
cd Coal/lm_track/coal_chat
pip install -r requirements.txt
pip install tokenizers datasets transformers accelerate
```

## 1. Train the tokenizer (once, ~30 min on node)

```bash
python tokenizer_train.py --sample-gb 4 --vocab 50304
# gate: report.json roundtrip > 0.95
```

## 2. Preflight (must pass before spending)

```bash
python gpu/preflight.py --gpus 10 --need-gb 90 --data-dir $COAL_DATA/tok
# exits non-zero on any FAIL
```

## 3. Stages

| Stage | Command | Time (FP8) | Cost | Gate |
|-------|---------|-----------|------|------|
| 1 fetch+tokenize | `bash gpu/stage1_fetch.sh` | ~3h | ~$90 | `pack_shards --check` passes |
| 2 pretrain | `bash gpu/stage2_pretrain.sh` | ~2.8h | ~$85 | val loss dropping, no NaN |
| 3 SFT | `bash gpu/stage3_sft.sh` | ~1h | ~$30 | loss drops, no collapse |
| 4 align | `bash gpu/stage4_align.sh` | ~2h | ~$60 | DPO margin rises |
| 5 eval+export | `bash gpu/stage5_eval.sh` | ~1h | ~$30 | eval_report.json produced |

**Total wall ~10h, ~$295.** (Tokenize can run concurrently with early
pretrain warmup; fetch can start before the clock if data is pre-staged.)

## 4. What each stage produces

```
$CKPT/v2.pt              pretrained base
$CKPT/sft_v2.pt          instruction-tuned
$CKPT/aligned_dpo.pt     DPO
$CKPT/aligned_kto.pt     KTO
$CKPT/aligned_orpo.pt    ORPO
$CKPT/mopd.pt            multi-teacher distilled (if teachers given)
$OUT/coal_int8.pt         deployable int8
$OUT/coal_int4.pt         deployable int4
$OUT/eval_report.json    benchmarks + qa + memory + safety
```

## 5. Resume after any crash

Every stage checkpoints. Re-running the same command resumes:

```bash
bash gpu/stage2_pretrain.sh     # picks up from $CKPT/v2.pt step
```

## 6. Safeguards wired (already tested on CPU)

- `rental_guardian` watchdog: ckpt every 30 min + $ burn tracking
- `sentinel_hooks`: balance-bias update, parity probe, governor
- `lambda_governor`: EME hysteresis control (collapse escape)
- checkpoint atomic write (`save_ckpt` uses tmp+replace)

## 7. Post-run: local deployment

```bash
# on your 24GB desktop
python local_run.py --selftest                 # detects RAM -> tier
python chat_v2.py --model artifacts/coal_int8.pt --tokenizer tokenizer_v2
```

## 8. Honest expectations (see also PLAN_500M_1B.md)

At 100B tokens + instruction pre-training (~300B effective):
- matches SmolLM2-360M on ARC/MMLU/PIQA/IFEval
- trails on HellaSwag/MT-Bench/HumanEval
- **owns**: memory (cross-session), grounding, coding guidance, safety
- does NOT beat SmolLM2 overall (they used 4T tokens)

## 9. If something fails

| Symptom | Fix |
|---------|-----|
| OOM on H200 | lower `micro_batch` in config_v2 |
| NCCL hang | `export NCCL_DEBUG=INFO`, check IB |
| tokenizer roundtrip < 0.95 | more sample data, retrain |
| val loss spikes | lower LR, check data shards |
| FP8 errors | unset `COAL_FP8` (BF16 fallback) |
