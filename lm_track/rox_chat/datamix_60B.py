"""60B-token data manifest for the 500M run (overtrained ~120x params,
Llama-style inference-optimal, not Chinchilla-minimal).

Holdings (ship to bucket, never re-download) + fresh pulls (node BW).
Weights are sampling ratios per epoch; dedupe runs first (pipeline.py
MinHash vs existing shards). Tokenizer: GPT-2 BPE 50,257 (MIT, zero
train time) — est ~4 chars/token on web/convo text.
"""
HOLDINGS = [
    # (path, raw_GB, est_tokens_B, weight, role)
    ("data/corpus/*.jsonl", 20.7, 5.0, 0.30, "pretrain web base"),
    ("data/corpus_multi/*", 1.7, 0.4, 0.05, "multilingual top-up"),
    ("data/large_raw/c4_en_*.jsonl", 30.0, 7.5, 0.20, "web volume"),
    ("data/human_convo/human_convo.jsonl", 1.0, 0.25, 0.10, "dialogue"),
    ("data/large_raw/openorca.jsonl", 1.7, 0.4, 0.10, "instruction-ish"),
]

FRESH = [
    # (hf_id, raw_GB, est_tokens_B, weight, role, license)
    ("Open-Orca/SlimOrca", 2.5, 0.6, 0.08, "SFT-quality pretrain", "MIT"),
    ("teknium/OpenHermes-2.5", 5.5, 1.4, 0.10, "convo volume", "mixed-permissive"),
    ("OpenAssistant/oasst2", 1.5, 0.35, 0.04, "human multi-turn", "Apache-2.0"),
    ("HuggingFaceH4/ultrachat_200k", 4.0, 1.0, 0.03, "long dialog", "mixed-permissive"),
]

SFT_RESERVED = [  # kept OUT of pretrain; SFT stage only
    "data/sft/sft_pairs.jsonl (1.6GB)",
    "data/large_raw/dolly.jsonl",
]

TOTAL_TOKENS_B = sum(t for _, _, t, _, _ in HOLDINGS) + \
    sum(t for _, _, t, _, _, _ in FRESH)
# 5.0+0.4+7.5+0.25+0.4 + 0.6+1.4+0.35+1.0 = ~16.9B unique -> ~3.5 epochs
# to reach 60B training tokens. Epoch mixing logged per run.


def manifest():
    w = sum(w for _, _, _, w, _ in HOLDINGS) + \
        sum(w for _, _, _, w, _, _ in FRESH)
    assert abs(w - 1.0) < 0.01, f"weights sum to {w}, must be 1.0"
    return {"holdings": HOLDINGS, "fresh": FRESH,
            "unique_tokens_B": round(TOTAL_TOKENS_B, 1),
            "epochs_for_60B": round(60 / TOTAL_TOKENS_B, 2),
            "sft_reserved": SFT_RESERVED}


if __name__ == "__main__":
    import json
    m = manifest()
    print(json.dumps(m, indent=1))
