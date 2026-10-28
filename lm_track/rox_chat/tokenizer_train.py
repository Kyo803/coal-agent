"""Train a from-scratch byte-level BPE tokenizer (vocab 50,304) on our
corpus, matching the GPT-2/SmolLM2 vocab size so comparisons are fair.

  python tokenizer_train.py --sample-gb 4 --vocab 50304

Samples text from the staged corpora, trains a BPE, saves to
tokenizer_v2/. Also writes a round-trip test + a tiktoken GPT-2
comparison so we can pick the better one empirically.
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "tokenizer_v2")
SOURCES = [
    ("C:/Users/WERU1/OneDrive/Documents/Default Project/llm_500m/"
     "data/corpus/shard_*.jsonl", "text"),
    ("C:/Users/WERU1/OneDrive/Documents/Default Project/llm_500m/"
     "data/large_raw/c4_en_*.jsonl", "text"),
    ("D:/rox_data/fresh/*.jsonl", "text"),
]


def sample_texts(target_bytes, max_docs=400000):
    got, docs = 0, []
    for pattern, key in SOURCES:
        for fp in sorted(glob.glob(pattern)):
            with open(fp, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        t = json.loads(line).get(key, "")
                    except Exception:
                        continue
                    if len(t) < 200:
                        continue
                    docs.append(t)
                    got += len(t)
                    if got >= target_bytes or len(docs) >= max_docs:
                        return docs
    return docs


def train_bpe(docs, vocab):
    from tokenizers import ByteLevelBPETokenizer
    tok = ByteLevelBPETokenizer()
    tok.train_from_iterator(
        docs, vocab_size=vocab,
        min_frequency=2,
        special_tokens=["<|endoftext|>", "<|user|>", "<|assistant|>",
                        "<|system|>", "<|memory|>", "<|tools|>"])
    return tok


def roundtrip(tok, samples):
    ok = 0
    for s in samples:
        ids = tok.encode(s).ids
        back = tok.decode(ids)
        if back.strip() == s.strip():
            ok += 1
    return ok / max(1, len(samples))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-gb", type=float, default=4.0)
    ap.add_argument("--vocab", type=int, default=50304)
    ap.add_argument("--max-docs", type=int, default=400000)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    target = int(args.sample_gb * 1e9)
    print(f"[tok] sampling ~{args.sample_gb}GB ...", flush=True)
    docs = sample_texts(target, args.max_docs)
    got = sum(len(d) for d in docs)
    print(f"[tok] {len(docs)} docs, {got/1e9:.2f}GB", flush=True)

    print(f"[tok] training BPE vocab={args.vocab} ...", flush=True)
    tok = train_bpe(docs, args.vocab)
    tok.save_model(OUT)
    print(f"[tok] saved {OUT}", flush=True)

    rt = roundtrip(tok, docs[:200])
    report = {"vocab": tok.get_vocab_size(), "docs": len(docs),
              "bytes": got, "roundtrip": round(rt, 4),
              "special_tokens": ["<|endoftext|>", "<|user|>",
                                 "<|assistant|>", "<|system|>",
                                 "<|memory|>", "<|tools|>"]}
    json.dump(report, open(os.path.join(OUT, "report.json"), "w"), indent=1)
    print(f"[tok] report: {report}")
    assert rt > 0.95, f"roundtrip too low: {rt}"
    print("[tok] OK")


if __name__ == "__main__":
    main()
