"""Before/after: base instruct model vs our SFT rox_brain on the 36-QA
factuality set + identity probe. Run: python eval_brain.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hf_backend import HFDraft, norm  # noqa: E402

QA = json.load(open(os.path.join(os.path.dirname(HERE), "str_trigger",
                                 "qa_set.json"), encoding="utf-8"))
BRAIN = os.path.join(HERE, "rox_brain")
BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"


def run(model_id, label, prefer_local):
    d = HFDraft(model_id=model_id, max_new=40, prefer_local=prefer_local)
    ok = 0
    for item in QA:
        d.history = []  # independent questions, not a conversation
        txt, _, _, _ = d.draft_fn(item["q"])
        g, o = norm(item["a"]), norm(txt)
        hit = bool(g) and bool(o) and (g in o or o in g)
        ok += hit
    ident, _, _, _ = d.draft_fn("Who are you? Answer in a few words.")
    return {"acc": round(ok / len(QA), 3), "n": len(QA),
            "identity": ident[:80]}


def main():
    out = {}
    for label, mid, pref in (("base", BASE, False), ("ours", BRAIN, True)):
        print(f"[eval_brain] running {label}...", flush=True)
        out[label] = run(mid, label, pref)
        print(f"[eval_brain] {label}: {out[label]}", flush=True)
    json.dump(out, open(os.path.join(HERE, "brain_eval.json"), "w"),
              indent=1)
    print("[eval_brain] done:", out)


if __name__ == "__main__":
    main()
