"""Conversational-first 60B manifest (replaces web-volume datamix_60B).

Honest premise: ~60B tokens of PURE human conversation does not exist
publicly. Real human dialogue available ≈ 7-9B tokens. This manifest
puts ALL of it first (upweighted by repeat sampling), then
instruction-dialogue, then English-teaching foundation (edu + books +
clean web English). Categories are labeled so ablations can measure
what the dialogue actually buys.

Token figures are estimates (~4 chars/token); the node run re-measures
exact counts at stage-in and re-normalizes weights. SFT pairs stay
reserved (never in pretrain).
"""
# (source, tokens_B_est, weight, category, license, note)
HUMAN_DIALOGUE = [
    ("lmsys/lmsys-chat-1m", 2.0, 0.10, "human",
     "gated/approval", "real user chats; skip if access denied"),
    ("allenai/WildChat-1M", 2.5, 0.10, "human",
     "non-commercial", "real user chats, research-ok per plan"),
    ("OpenAssistant/oasst2", 0.15, 0.04, "human",
     "Apache-2.0", "human multi-turn gold, small but dense"),
    ("allenai/soda", 1.2, 0.04, "human-distilled",
     "Apache-2.0", "social dialogue, synthetic but conversational"),
    ("HuggingFaceH4/ultrachat_200k", 0.8, 0.04, "model-dialog",
     "mixed-permissive", "long multi-turn shape"),
    ("Anthropic/hh-rlhf", 0.3, 0.02, "human-pref",
     "MIT", "chosen responses double as SFT dialogue"),
    ("local:data/human_convo/human_convo.jsonl", 0.25, 0.03, "human-mix",
     "mixed", "already held, do not re-download"),
]

INSTRUCTION_DIALOG = [
    ("teknium/OpenHermes-2.5", 1.5, 0.08, "instruct",
     "mixed-permissive", "single-turn heavy, chat-shaped"),
    ("Open-Orca/OpenOrca-full", 5.0, 0.08, "instruct",
     "MIT", "fresh full pull; local 1.7GB is a subset"),
    ("Open-Orca/SlimOrca", 0.5, 0.03, "instruct",
     "MIT", "quality-filtered orca"),
]

ENGLISH_TEACHING = [
    ("HuggingFaceFW/fineweb-edu sample", 25.0, 0.22, "edu-english",
     "mixed-permissive", "stream 25B, do NOT full-download 1.3T"),
    ("Gutenberg PG slice (books)", 2.0, 0.05, "books-english",
     "public-domain", "long-form grammar + narrative"),
    ("local:data/large_raw/c4_en_*.jsonl (subset)", 7.0, 0.08, "web-english",
     "mixed", "already held; clean EN slice only"),
    ("local:data/corpus EN subset", 5.0, 0.06, "web-english",
     "mixed", "already held; EN + quality gates"),
    ("local:data/corpus_multi (top-up)", 0.4, 0.03, "multilingual",
     "mixed", "kept small: English-first per spec"),
]

SFT_RESERVED = ["data/sft/sft_pairs.jsonl (1.6GB)", "data/large_raw/dolly.jsonl"]


def manifest(target_B=60.0):
    groups = {"human_dialogue": HUMAN_DIALOGUE,
              "instruction_dialog": INSTRUCTION_DIALOG,
              "english_teaching": ENGLISH_TEACHING}
    w = sum(r[2] for g in groups.values() for r in g)
    assert abs(w - 1.0) < 0.015, f"weights sum to {w}"
    toks = {k: round(sum(r[1] for r in v), 2) for k, v in groups.items()}
    total = round(sum(toks.values()), 2)
    convo = round(toks["human_dialogue"] + toks["instruction_dialog"], 2)
    return {
        "groups": {k: [{"source": r[0], "tokens_B": r[1], "weight": r[2],
                        "license": r[4], "note": r[5]} for r in v]
                  for k, v in groups.items()},
        "tokens_by_group_B": toks,
        "unique_total_B": total,
        "conversational_B": convo,
        "conversational_share": round(convo / total, 3),
        "epochs_for_60B": round(target_B / total, 2),
        "dialogue_oversample": "human_dialogue weight (0.37) exceeds its "
                               "token share (~0.13): deliberate repeat "
                               "sampling so the model lives in dialogue",
        "sft_reserved": SFT_RESERVED,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(manifest(), indent=1))
