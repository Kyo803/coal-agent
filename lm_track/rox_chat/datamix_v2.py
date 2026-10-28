"""Compute the 100B code-first data manifest from staged + fetched sources.

Estimates tokens (~4 chars/token), applies the mix weights, and emits
data_manifest.json consumed by tokenize_corpus.py.

  python datamix_v2.py --target-b 100 --out data_manifest.json
"""
import argparse
import glob
import json
import os

ROOT = "C:/Users/WERU1/OneDrive/Documents/Default Project"
GB = 1024 ** 3

# source registry: (key, glob, kind, role)
LOCAL = [
    ("corpus", f"{ROOT}/llm_500m/data/corpus/shard_*.jsonl", "text",
     "conversation"),
    ("large_raw", f"{ROOT}/llm_500m/data/large_raw/*.jsonl", "text",
     "web"),
    ("fresh", "D:/rox_data/fresh/*.jsonl", "text", "conversation"),
    ("code", "D:/rox_data/code/*.jsonl", "text", "code"),
    ("instr", "D:/rox_data/instr/*.jsonl", "text", "instruction"),
]

# remote sources streamed on-node (not local files): estimated tokens
REMOTE = [
    ("fineweb_edu", 25e9, "web"),
    ("finemath", 8e9, "math"),
]


def measure(pattern):
    total = 0
    files = 0
    for fp in glob.glob(pattern):
        if "fetch_report" in fp or "manifest" in fp:
            continue
        try:
            total += os.path.getsize(fp)
            files += 1
        except OSError:
            pass
    return total, files


def build(target_b=100.0):
    kinds = {}
    detail = {}
    for key, pattern, _t, kind in LOCAL:
        b, n = measure(pattern)
        est = b / 4.0
        kinds[kind] = kinds.get(kind, 0) + est
        detail[key] = {"bytes": b, "files": n, "est_tokens": est,
                       "kind": kind}
    for key, est, kind in REMOTE:
        kinds[kind] = kinds.get(kind, 0) + est
        detail[key] = {"bytes": None, "files": None, "est_tokens": est,
                       "kind": kind, "remote": True}

    target = target_b * 1e9
    # desired share per mix
    mix = {"web": 0.30, "code": 0.30, "math": 0.12,
           "conversation": 0.18, "instruction": 0.10}
    plan = {}
    for kind, share in mix.items():
        want = target * share
        have = kinds.get(kind, 0.0)
        plan[kind] = {
            "want_tokens": want,
            "have_tokens": have,
            "repeat": round(want / have, 2) if have > 0 else None,
            "short": have < want,
        }
    return {"target_tokens": target, "mix": mix,
            "kinds": {k: round(v, 0) for k, v in kinds.items()},
            "plan": plan, "sources": detail}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-b", type=float, default=100.0)
    ap.add_argument("--out", default="data_manifest.json")
    args = ap.parse_args()
    m = build(args.target_b)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.out)
    json.dump(m, open(out, "w"), indent=1)
    print(json.dumps(m["plan"], indent=1))
    print(f"\n[datamix] staged kinds (tokens): "
          f"{ {k: f'{v/1e9:.2f}B' for k, v in m['kinds'].items()} }")
    short = [k for k, v in m["plan"].items() if v["short"]]
    if short:
        print(f"[datamix] SHORT on: {short} (fetch or repeat more)")
    print(f"[datamix] wrote {out}")


if __name__ == "__main__":
    main()
