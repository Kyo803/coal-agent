#!/usr/bin/env bash
# Stage 1: fetch + tokenize ~100B tokens. Run on the GPU node.
# Time ~3h (node bandwidth). Idempotent/resumable.
set -euo pipefail
cd "$(dirname "$0")/.."

DATA="${ROX_DATA:-/data/rox}"
echo "[stage1] data root: $DATA"
mkdir -p "$DATA"/{code,instr,tok}

# 1a. fetch code + math corpora (streaming, resumable)
python fetch_code.py --outdir "$DATA/code"

# 1b. instruction pre-training augmentation (FIM + templates)
python instruction_augment.py --in "$DATA/code" --out "$DATA/instr/instr_aug.jsonl"

# 1c. data manifest (code-first mix)
python datamix_v2.py --target-b "${ROX_TOKENS_B:-100}" --out data_manifest.json

# 1d. tokenize to uint16 shards
python tokenize_corpus.py \
  --manifest data_manifest.json \
  --tokenizer tokenizer_v2 \
  --out "$DATA/tok" \
  --target-b "${ROX_TOKENS_B:-100}"

# 1e. validate shards
python pack_shards.py --dir "$DATA/tok" --check

echo "[stage1] done"
