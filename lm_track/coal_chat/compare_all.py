"""Compare all trained models on the 36-QA factuality set + identity."""
import json
import os
import sys

import torch
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hf_backend import HFDraft, norm  # noqa: E402

QA = json.load(open(os.path.join(os.path.dirname(HERE), "str_trigger",
                                 "qa_set.json"), encoding="utf-8"))

MODELS = {
    "base": "HuggingFaceTB/SmolLM2-135M-Instruct",
    "sft": os.path.join(HERE, "coal_brain"),
    "kto": os.path.join(HERE, "coal_kto"),
    "orpo": os.path.join(HERE, "coal_orpo"),
    "online_dpo": os.path.join(HERE, "coal_online_dpo"),
}


def eval_model(label, model_id):
    d = HFDraft(model_id=model_id, max_new=40, prefer_local=False)
    ok = 0
    for item in QA:
        d.history = []
        txt, _, _, _ = d.draft_fn(item["q"])
        g, o = norm(item["a"]), norm(txt)
        hit = bool(g) and bool(o) and (g in o or o in g)
        ok += hit
    ident, _, _, _ = d.draft_fn("Who are you? Answer briefly.")
    return {"acc": round(ok / len(QA), 3), "n": len(QA),
            "identity": ident[:80]}


def main():
    results = {}
    for label, mid in MODELS.items():
        print(f"[compare] {label}...", flush=True)
        results[label] = eval_model(label, mid)
        print(f"[compare] {label}: {results[label]}", flush=True)
    json.dump(results, open(os.path.join(HERE, "model_compare.json"), "w"),
              indent=1)
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
