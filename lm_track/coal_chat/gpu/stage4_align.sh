#!/usr/bin/env bash
# Stage 4: alignment. DPO -> KTO -> ORPO -> GRPO -> MOPD, chained.
# Time ~2-3h on 10x H200 (or run a subset).
set -euo pipefail
cd "$(dirname "$0")/.."

NGPU="${NGPU:-10}"
TIER="${ROX_TIER:-500M}"
DATA="${ROX_DATA:-/data/rox}"
CKPT="${CHECKPOINT_OFFLOAD:-$PWD/ckpt_v2}"
BASE="${ROX_BASE:-$CKPT/sft_v2.pt}"

# preference sources
PREFS_DPO="${ROX_PREFS_DPO:-$DATA/atp/atp_dpo.jsonl}"
PREFS_SAFE="${ROX_PREFS_SAFE:-$DATA/safety/safety_dpo.jsonl}"

# DPO (persona + atp + safety)
torchrun --nproc_per_node="$NGPU" --standalone \
  align_v2.py --method dpo --tier "$TIER" --base "$BASE" \
  --prefs "$PREFS_DPO" --ckpt "$CKPT" --steps 500 --beta 0.1

# KTO (unpaired, safety)
torchrun --nproc_per_node="$NGPU" --standalone \
  align_v2.py --method kto --tier "$TIER" \
  --base "$CKPT/aligned_dpo.pt" --prefs "$PREFS_SAFE" \
  --ckpt "$CKPT" --steps 300 --beta 0.5

# ORPO (fused sft+pref)
torchrun --nproc_per_node="$NGPU" --standalone \
  align_v2.py --method orpo --tier "$TIER" \
  --base "$CKPT/aligned_kto.pt" --prefs "$PREFS_DPO" \
  --ckpt "$CKPT" --steps 300

# GRPO (rule-based rewards) — reuses the existing runner
[ "${ROX_SKIP_GRPO:-0}" = "1" ] || \
  python run_grpo.py --steps 100 || echo "[stage4] grpo skipped"

# MOPD (multi-teacher distill) if teachers exist
[ -n "${ROX_TEACHERS:-}" ] && \
  python mopd.py --tier "$TIER" --student "$CKPT/aligned_orpo.pt" \
    --teachers "$ROX_TEACHERS" --domains "$DATA/mopd" --ckpt "$CKPT" \
    || echo "[stage4] mopd skipped (no teachers)"

echo "[stage4] done"
