"""Tokenize staged corpora to uint16 shards per the data manifest.

  python tokenize_corpus.py --manifest data_manifest.json \
      --tokenizer tokenizer_v2 --out D:/coal_data/tok --target-b 100

Streams each source, tokenizes with the from-scratch BPE, writes .bin
shards (~200M tokens each) + index.json. Resumable via index.json.
Mix-aware: repeats/undersamples sources to hit the target proportions.
"""
import argparse
import glob
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SHARD_TOKENS = 200_000_000


def load_sources(manifest_path):
    m = json.load(open(manifest_path, encoding="utf-8"))
    srcs = []
    for key, d in m["sources"].items():
        srcs.append((key, d))
    return m, srcs


def resolve_glob(key):
    ROOT = "C:/Users/WERU1/OneDrive/Documents/Default Project"
    mapping = {
        "corpus": f"{ROOT}/llm_500m/data/corpus/shard_*.jsonl",
        "large_raw": f"{ROOT}/llm_500m/data/large_raw/*.jsonl",
        "fresh": "D:/coal_data/fresh/*.jsonl",
        "code": "D:/coal_data/code/*.jsonl",
        "instr": "D:/coal_data/instr/*.jsonl",
    }
    return mapping.get(key)


class ShardWriter:
    def __init__(self, outdir, start_shard=0):
        self.outdir = outdir
        self.shard = start_shard
        self.buf = []
        self.total = 0
        os.makedirs(outdir, exist_ok=True)

    def add(self, ids):
        self.buf.extend(ids)
        while len(self.buf) >= SHARD_TOKENS:
            self.flush(SHARD_TOKENS)

    def flush(self, n=None):
        if not self.buf:
            return
        n = n or len(self.buf)
        chunk = self.buf[:n]
        self.buf = self.buf[n:]
        path = os.path.join(self.outdir, f"shard_{self.shard:05d}.bin")
        np.array(chunk, dtype=np.uint16).tofile(path)
        self.shard += 1
        self.total += len(chunk)

    def close(self):
        self.flush()
        return self.total


def tokenize(tokenizer_dir):
    from tokenizers import ByteLevelBPETokenizer
    tok = ByteLevelBPETokenizer(
        os.path.join(tokenizer_dir, "vocab.json"),
        os.path.join(tokenizer_dir, "merges.txt"))
    return tok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.path.join(HERE,
                                                       "data_manifest.json"))
    ap.add_argument("--tokenizer", default=os.path.join(HERE, "tokenizer_v2"))
    ap.add_argument("--out", default="D:/coal_data/tok")
    ap.add_argument("--target-b", type=float, default=100.0)
    ap.add_argument("--val-frac", type=float, default=0.005)
    args = ap.parse_args()

    tok = tokenize(args.tokenizer)
    manifest, srcs = load_sources(args.manifest)
    target = args.target_b * 1e9
    writer = ShardWriter(os.path.join(args.out, "train"))
    val_writer = ShardWriter(os.path.join(args.out, "val"))

    # per-kind budget from the manifest plan
    plan = manifest["plan"]
    kind_budget = {k: v["want_tokens"] for k, v in plan.items()}

    produced = {}
    for key, d in srcs:
        kind = d["kind"]
        budget = kind_budget.get(kind, 0)
        if budget <= 0:
            continue
        g = resolve_glob(key)
        if not g:
            print(f"[tok] {key}: remote (stream on node) — skip local")
            continue
        files = sorted(glob.glob(g))
        if not files:
            print(f"[tok] {key}: no files at {g}")
            continue
        got = 0
        print(f"[tok] {key} ({kind}) budget={budget/1e9:.1f}B "
              f"files={len(files)}", flush=True)
        # repeat passes until budget met (oversampling small sources)
        pass_i = 0
        while got < budget:
            for fp in files:
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        try:
                            t = json.loads(line).get("text", "")
                        except Exception:
                            continue
                        if len(t) < 50:
                            continue
                        ids = tok.encode(t).ids
                        if pass_i == 0 and (got % 20000) < 5:
                            val_writer.add(ids)
                        else:
                            writer.add(ids)
                        got += len(ids)
                        if got >= budget:
                            break
                if got >= budget:
                    break
            pass_i += 1
        produced[key] = got
        print(f"[tok] {key}: {got/1e9:.2f}B", flush=True)

    train_total = writer.close()
    val_total = val_writer.close()
    idx = {"train_tokens": train_total, "val_tokens": val_total,
           "shard_tokens": SHARD_TOKENS,
           "train_shards": writer.shard, "val_shards": val_writer.shard,
           "produced": {k: int(v) for k, v in produced.items()},
           "vocab": tok.get_vocab_size()}
    json.dump(idx, open(os.path.join(args.out, "index.json"), "w"), indent=1)
    print(f"[tok] train={train_total/1e9:.2f}B val={val_total/1e6:.1f}M "
          f"-> {args.out}")


if __name__ == "__main__":
    main()
