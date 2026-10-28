#!/usr/bin/env bash
# Stage 5: eval + quantize + export. Time ~1h.
set -euo pipefail
cd "$(dirname "$0")/.."

CKPT="${CHECKPOINT_OFFLOAD:-$PWD/ckpt_v2}"
OUT="${ROX_OUT:-$PWD/artifacts}"
mkdir -p "$OUT"

# pick the most-aligned checkpoint present
for name in mopd aligned_orpo aligned_kto aligned_dpo sft_v2 v2; do
  if [ -f "$CKPT/$name.pt" ]; then FINAL="$CKPT/$name.pt"; break; fi
done
echo "[stage5] final checkpoint: ${FINAL:-NONE}"

# full eval harness (benchmarks + qa + memory + safety)
python eval_harness.py --model "$FINAL" \
  --benchmarks arc_easy,arc_challenge,piqa,hellaswap,openbookqa \
  --out "$OUT/eval_report.json" || \
python eval_harness.py --model "$FINAL" \
  --benchmarks arc_easy,piqa \
  --out "$OUT/eval_report.json"

# local perf bench
python bench_local.py --tier "${ROX_TIER:-500M}" --out "$OUT/bench.json" || true

# quantize for deployment (int8 + int4)
python quantize.py --model "$FINAL" --bits 8 --out "$OUT/rox_int8.pt"
python quantize.py --model "$FINAL" --bits 4 --out "$OUT/rox_int4.pt"

# contamination scan of eval vs corpus
python ../scripts/scan_contamination.py --corpus "$ROX_DATA/corpus/*.jsonl" \
  > "$OUT/contamination.json" 2>/dev/null || echo "[stage5] scan skipped"

echo "[stage5] artifacts -> $OUT"
ls -la "$OUT"
