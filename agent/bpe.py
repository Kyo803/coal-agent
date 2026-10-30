"""Minimal byte-level BPE (32K target for 500M; tiny demo: 500 merges).

Trains on raw text (no labels, no questions): count adjacent pairs,
merge the most frequent, repeat. cpu_test(): roundtrip + compression
on held-out text. Production trains on llm_500m corpus slices.
"""
import json
from collections import Counter


def train_bpe(texts, vocab_size=500, max_merges=None):
    ids_list = [list(t.encode("utf-8", errors="ignore")) for t in texts]
    merges = {}
    n = max_merges or (vocab_size - 256)
    for _ in range(n):
        counts = Counter()
        for ids in ids_list:
            for a, b in zip(ids, ids[1:]):
                counts[(a, b)] += 1
        if not counts:
            break
        (a, b), f = counts.most_common(1)[0]
        if f < 2:
            break
        tok = 256 + len(merges)
        merges[(a, b)] = tok
        ids_list = [merge_ids(ids, a, b, tok) for ids in ids_list]
    return {"merges": [[a, b, t] for (a, b), t in merges.items()]}


def merge_ids(ids, a, b, tok):
    out, i = [], 0
    while i < len(ids):
        if i < len(ids) - 1 and ids[i] == a and ids[i + 1] == b:
            out.append(tok)
            i += 2
        else:
            out.append(ids[i])
            i += 1
    return out


def encode(text, model):
    ids = list(text.encode("utf-8", errors="ignore"))
    for a, b, tok in model["merges"]:
        ids = merge_ids(ids, a, b, tok)
    return ids


def vocab_size(model):
    return 256 + len(model["merges"])


def cpu_test():
    texts = ["Once upon a time there was a little girl. " * 20,
             "The quick brown fox jumps over the lazy dog. " * 20,
             "Hello world, this is a tokenizer test. " * 20]
    m = train_bpe(texts, vocab_size=500)
    s = "Once upon a time a fox met a girl."
    ids = encode(s, m)
    raw = list(s.encode())
    print(f"[bpe] vocab={vocab_size(m)} raw={len(raw)}bpe={len(ids)} "
          f"ratio={len(ids) / len(raw):.2f}")
    assert len(ids) < len(raw), "no compression learned"
    json.dump(m, open("bpe_demo.json", "w"))
    print("[bpe] OK")
    return True


if __name__ == "__main__":
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(0 if cpu_test() else 1)
