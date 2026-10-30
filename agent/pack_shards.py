"""Validate tokenized shards + provide the memmap loader used by training.

  python pack_shards.py --dir D:/coal_data/tok --check

Flat uint16 shards are directly trainable (memmap + random windows);
this validates integrity, reports exact counts, and exposes load_shards().
"""
import argparse
import glob
import json
import os

import numpy as np


def load_shards(split_dir):
    """Returns a list of np.memmap uint16 arrays (one per shard)."""
    paths = sorted(glob.glob(os.path.join(split_dir, "*.bin")))
    return [np.memmap(p, dtype=np.uint16, mode="r") for p in paths]


class ShardSampler:
    """Random contiguous windows across all shards (train/val)."""

    def __init__(self, split_dir, seq_len=4096, seed=0):
        self.shards = load_shards(split_dir)
        self.lens = np.array([len(s) for s in self.shards], dtype=np.int64)
        self.total = int(self.lens.sum())
        self.seq_len = seq_len
        self.rng = np.random.default_rng(seed)
        assert self.total > seq_len, f"not enough tokens: {self.total}"

    def batch(self, n, seq_len=None):
        seq_len = seq_len or self.seq_len
        out = np.empty((n, seq_len), dtype=np.int64)
        for i in range(n):
            si = int(self.rng.integers(0, len(self.shards)))
            hi = self.lens[si] - seq_len
            start = int(self.rng.integers(0, hi))
            out[i] = self.shards[si][start:start + seq_len]
        return out


def check(outdir):
    idx_path = os.path.join(outdir, "index.json")
    idx = json.load(open(idx_path)) if os.path.exists(idx_path) else {}
    report = {}
    for split in ("train", "val"):
        d = os.path.join(outdir, split)
        if not os.path.isdir(d):
            continue
        shards = load_shards(d)
        total = sum(len(s) for s in shards)
        mx = 0
        for s in shards:
            if len(s):
                mx = max(mx, int(s.max()))
        report[split] = {"shards": len(shards), "tokens": int(total),
                         "max_token_id": mx}
        print(f"[pack] {split}: {len(shards)} shards, "
              f"{total/1e9:.3f}B tokens, max_id={mx}")
    vocab = idx.get("vocab", 50304)
    bad = [k for k, v in report.items() if v["max_token_id"] >= vocab]
    if bad:
        print(f"[pack] FAIL: token ids exceed vocab in {bad}")
        return 1
    if report.get("train", {}).get("tokens", 0) < 1e9:
        print("[pack] WARN: < 1B train tokens staged")
    print(f"[pack] OK vocab={vocab} index={idx}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="D:/coal_data/tok")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        raise SystemExit(check(args.dir))
    print("use --check")


if __name__ == "__main__":
    main()
