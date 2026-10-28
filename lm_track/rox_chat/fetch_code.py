"""Fetch code + math corpora for the 100B code-first mix.

Streams HF datasets, writes unified JSONL {text, source} capped per
source, resumable. Designed to run on the GPU node (fast bandwidth);
--test fetches a tiny sample locally.

  python fetch_code.py --outdir D:/rox_data/code --test
  python fetch_code.py --outdir /data/rox/code          # on node
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GB = 1024 ** 3

# (tag, hf_id, config, split, cap_bytes, kind)
SOURCES = [
    ("stack_edu", "HuggingFaceTB/stack-edu", "python", "train", 30 * GB,
     "code"),
    ("stack_edu_js", "HuggingFaceTB/stack-edu", "javascript", "train",
     8 * GB, "code"),
    ("stack_edu_ts", "HuggingFaceTB/stack-edu", "typescript", "train",
     6 * GB, "code"),
    ("stack_edu_java", "HuggingFaceTB/stack-edu", "java", "train",
     5 * GB, "code"),
    ("stack_edu_cpp", "HuggingFaceTB/stack-edu", "cpp", "train",
     5 * GB, "code"),
    ("stack_edu_rust", "HuggingFaceTB/stack-edu", "rust", "train",
     3 * GB, "code"),
    ("finemath", "HuggingFaceTB/finemath", "finemath-4plus", "train",
     10 * GB, "math"),
    ("instruct_webmath", "HuggingFaceTB/infimm-webmath-40b", None,
     "train", 5 * GB, "math"),
    ("stack_edu_bash", "HuggingFaceTB/stack-edu", "shell", "train",
     2 * GB, "code"),
    ("stack_edu_go", "HuggingFaceTB/stack-edu", "go", "train",
     3 * GB, "code"),
]


def extract(ex):
    for k in ("content", "text", "code", "problem", "solution"):
        v = ex.get(k)
        if isinstance(v, str) and len(v) > 40:
            return v[:8000]
    # math datasets: problem + solution
    p, s = ex.get("problem", ""), ex.get("solution", "")
    if p and s:
        return f"Problem: {p[:2000]}\nSolution: {s[:4000]}"
    return None


def row_count(path):
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def fetch_one(tag, hf_id, config, split, cap, outdir):
    from datasets import load_dataset
    path = os.path.join(outdir, f"{tag}.jsonl")
    done = row_count(path)
    if os.path.exists(path) and os.path.getsize(path) >= cap * 0.9:
        return {"status": "exists", "bytes": os.path.getsize(path)}
    ds = load_dataset(hf_id, config, split=split, streaming=True,
                      trust_remote_code=False)
    if done:
        ds = ds.skip(done)
    nbytes = os.path.getsize(path) if done else 0
    nrows = done
    with open(path, "a" if done else "w", encoding="utf-8") as f:
        for ex in ds:
            t = extract(ex)
            if not t:
                continue
            line = json.dumps({"text": t, "source": tag}) + "\n"
            f.write(line)
            nbytes += len(line.encode("utf-8", errors="ignore"))
            nrows += 1
            if nbytes >= cap:
                break
    return {"status": "ok" + (" (resumed)" if done else ""),
            "bytes": nbytes, "rows": nrows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="D:/rox_data/code")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--only", default=None)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    rep_path = os.path.join(args.outdir, "fetch_report.json")
    rep = {}
    if os.path.exists(rep_path):
        try:
            rep = json.load(open(rep_path, encoding="utf-8"))
        except Exception:
            rep = {}
    for tag, hf_id, config, split, cap, kind in SOURCES:
        if args.only and tag != args.only:
            continue
        if args.test:
            cap = 20 * 1024 * 1024  # 20MB test cap
        try:
            r = fetch_one(tag, hf_id, config, split, cap, args.outdir)
        except Exception as e:
            r = {"status": f"SKIP: {type(e).__name__}: {str(e)[:120]}"}
        r["kind"] = kind
        rep[tag] = r
        print(f"[code] {tag}: {r}", flush=True)
    json.dump(rep, open(rep_path, "w"), indent=1)
    tot = sum(v.get("bytes", 0) for v in rep.values()
              if isinstance(v, dict))
    print(f"[code] total {tot/1e9:.2f}GB -> {args.outdir}")


if __name__ == "__main__":
    main()
