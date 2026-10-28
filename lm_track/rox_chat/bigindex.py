"""Corpus-backed retrieval: inverted BM25 index over real corpus passages.

Replaces the 20 hand-written demo docs with up to 100K English passages
from llm_500m data/corpus shards (quality-filtered, chunked ~400 chars
for granularity). Same BM25 math + stopwords as retrieval.py; postings
restrict scoring to candidate docs (ms per query, not seconds).
Build once:  python bigindex.py --build [--max-docs N]
Use:         BigBM25.load(prefix) has .search(query, top) like BM25.
"""
import glob
import json
import math
import os
import pickle
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from retrieval import STOP  # noqa: E402

CORPUS_GLOB = ("C:/Users/WERU1/OneDrive/Documents/Default Project/"
               "llm_500m/data/corpus/shard_*.jsonl")


def toks(s):
    return [t for t in re.findall(r"[a-z0-9]+", s.lower())
            if t not in STOP and len(t) > 1]


def passages(text, width=400):
    text = re.sub(r"\s+", " ", text).strip()
    return [text[i:i + width] for i in range(0, len(text), width)
            if len(text[i:i + width]) > 120]


def build(corpus_glob=CORPUS_GLOB, out=None, max_docs=100000):
    from collections import Counter
    out = out or os.path.join(HERE, "bigindex")
    os.makedirs(out, exist_ok=True)
    docs, post, df = [], {}, Counter()
    for fp in sorted(glob.glob(corpus_glob)):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("lang") != "en" or d.get("quality") == "bad":
                    continue
                for p in passages(d.get("text", "")):
                    if len(docs) >= max_docs:
                        break
                    docs.append(p[:600])
                    for t in set(toks(p)):
                        post.setdefault(t, []).append(len(docs) - 1)
                        df[t] += 1
                if len(docs) >= max_docs:
                    break
        if len(docs) >= max_docs:
            break
        print(f"[bigindex] {len(docs)} passages...", flush=True)
    dl = [len(toks(p)) or 1 for p in docs]
    avg = sum(dl) / max(1, len(dl))
    with open(os.path.join(out, "passages.jsonl"), "w",
              encoding="utf-8") as f:
        for p in docs:
            f.write(json.dumps({"text": p}) + "\n")
    with open(os.path.join(out, "index.pkl"), "wb") as f:
        pickle.dump({"post": post, "df": dict(df), "dl": dl, "avg": avg,
                     "n": len(docs)}, f)
    print(f"[bigindex] done: {len(docs)} passages, "
          f"{len(post)} terms -> {out}")
    return out


class BigBM25:
    def __init__(self, prefix):
        with open(os.path.join(prefix, "index.pkl"), "rb") as f:
            d = pickle.load(f)
        self.post, self.df, self.dl = d["post"], d["df"], d["dl"]
        self.avg, self.n = d["avg"], d["n"]
        self.docs = [json.loads(l)["text"] for l in
                     open(os.path.join(prefix, "passages.jsonl"),
                          encoding="utf-8")]
        self.down = False

    @classmethod
    def load(cls, prefix):
        return cls(prefix)

    def search(self, query, top=2, k1=1.2, b=0.75):
        if self.down:
            return []
        from collections import Counter
        q = Counter(toks(query))
        scores = Counter()
        for t, f in q.items():
            if t not in self.post:
                continue
            idf = math.log(1 + (self.n - self.df[t] + 0.5)
                           / (self.df[t] + 0.5))
            for i in self.post[t]:
                c = toks(self.docs[i]).count(t)
                num = c * (k1 + 1)
                den = c + k1 * (1 - b + b * self.dl[i] / self.avg)
                scores[i] += idf * f * num / den
        best = scores.most_common(top)
        return [(self.docs[i], s) for i, s in best if s > 0]


if __name__ == "__main__":
    max_docs = 100000
    for a in sys.argv[1:]:
        if a.startswith("--max-docs="):
            max_docs = int(a.split("=", 1)[1])
    if "--build" in sys.argv:
        build(max_docs=max_docs)
    else:
        print("use --build [--max-docs N]")
