"""Raw text supply: TinyStories streamed from HF, byte-tokenised on the fly.
No questions, no answers, no labels — just stories. Cached to .pt files
so retraining doesn't re-download.
"""
import os

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
N_TRAIN_STORIES = 8000
N_VAL_STORIES = 300


def fetch():
    from datasets import load_dataset
    from model_gpt import encode
    ds = load_dataset("roneneldan/TinyStories", split="train",
                      streaming=True)
    train_toks, val_toks, n = [], [], 0
    for ex in ds:
        toks = encode(ex["text"][:2000] + "\n\n")
        (val_toks if n >= N_TRAIN_STORIES else train_toks).extend(toks)
        n += 1
        if n >= N_TRAIN_STORIES + N_VAL_STORIES:
            break
        if n % 2000 == 0:
            print(f"[data] {n} stories...", flush=True)
    tr = torch.tensor(train_toks, dtype=torch.long)
    va = torch.tensor(val_toks, dtype=torch.long)
    torch.save({"train": tr, "val": va},
               os.path.join(HERE, "tinystories.pt"))
    print(f"[data] train={len(tr) / 1e6:.2f}M toks val={len(va) / 1e3:.0f}k")
    return tr, va


def load():
    p = os.path.join(HERE, "tinystories.pt")
    if os.path.exists(p):
        d = torch.load(p, weights_only=True)
        return d["train"], d["val"]
    return fetch()
