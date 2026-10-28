#!/usr/bin/env bash
# Stage 3: SFT on instruction + conversation + memory-tools + safety.
# Time ~1h on 10x H200.
set -euo pipefail
cd "$(dirname "$0")/.."

NGPU="${NGPU:-10}"
TIER="${ROX_TIER:-500M}"
DATA="${ROX_DATA:-/data/rox}"
CKPT="${CHECKPOINT_OFFLOAD:-$PWD/ckpt_v2}"
BASE="${ROX_BASE:-$CKPT/v2.pt}"

# generate safety + atp training data if missing
[ -d "$DATA/safety" ] || python safety_data.py --out "$DATA/safety"
[ -d "$DATA/atp" ] || python atp_data.py --out "$DATA/atp"

torchrun --nproc_per_node="$NGPU" --standalone \
  sft_v2.py --tier "$TIER" --base "$BASE" --ckpt "$CKPT" \
  --steps 2000 --batch 4

echo "[stage3] done -> $CKPT/sft_v2.pt"
