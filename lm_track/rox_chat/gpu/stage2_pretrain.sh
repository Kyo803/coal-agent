#!/usr/bin/env bash
# Stage 2: pretrain 500M MoE on ~100B tokens. Run on the GPU node.
# 10x H200, FP8 ~2.8h (BF16 ~5h). Checkpoint every 200 steps.
set -euo pipefail
cd "$(dirname "$0")/.."

NGPU="${NGPU:-10}"
TIER="${ROX_TIER:-500M}"
TOKENS_B="${ROX_TOKENS_B:-100}"
DATA="${ROX_DATA:-/data/rox}"
CKPT="${CHECKPOINT_OFFLOAD:-$PWD/ckpt_v2}"
export HF_TOKEN="${HF_TOKEN:-}"

mkdir -p "$CKPT"

# preflight gate
python gpu/preflight.py --gpus "$NGPU" --need-gb 90 --data-dir "$DATA/tok"

# launch distributed pretraining
FP8_FLAG=""
[ "${ROX_FP8:-0}" = "1" ] && FP8_FLAG="--fp8"

torchrun --nproc_per_node="$NGPU" --standalone \
  train_v2.py --tier "$TIER" --tokens-b "$TOKENS_B" \
  --ckpt "$CKPT" $FP8_FLAG

echo "[stage2] done -> $CKPT/v2.pt"
