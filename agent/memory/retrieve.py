"""Hybrid retrieval over memory: BM25 (keyword) + vector (semantic),
fused by reciprocal-rank fusion, then reranked by recency x salience.

Returns memory items with provenance so the assembler can cite them.
"""
import math
import re
from collections import Counter

STOP = set("a an the is are was were be been to of in on for and or it "
           "this that i you he she we they my your what who where when "
           "how do does did".split())


def toks(s):
    return [t for t in re.findall(r"[a-z0-9]+", s.lower())
            if t not in STOP and len(t) > 1]


class _BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.td = [Counter(toks(d)) for d in docs]
        self.dl = [sum(c.values()) for c in self.td]
        self.avg = (sum(self.dl) / len(self.dl)) if self.dl else 1.0
        df = Counter()
        for c in self.td:
            for t in c:
                df[t] += 1
        n = max(1, len(docs))
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5))
                    for t, f in df.items()}
        self.k1, self.b = k1, b

    def score(self, query):
        q = Counter(toks(query))
        out = []
        for i, c in enumerate(self.td):
            s = 0.0
            for t, f in q.items():
                if t not in c:
                    continue
                num = c[t] * (self.k1 + 1)
                den = c[t] + self.k1 * (1 - self.b + self.b * self.dl[i]
                                        / self.avg)
                s += self.idf.get(t, 0.0) * f * num / den
            out.append((i, s))
        return out


class Retriever:
    def __init__(self, store, index, embedder):
        self.store = store
        self.index = index
        self.embedder = embedder

    def search(self, query, k=8, rerank=True):
        # candidate pool: recent + semantic + keyword
        recent = self.store.recent_messages(limit=200)
        ids = [m["id"] for m in recent]
        texts = [m["text"] for m in recent]
        by_id = {m["id"]: m for m in recent}
        if not ids:
            return []
        # BM25
        bm = _BM25(texts)
        bm_scores = {ids[i]: s for i, s in bm.score(query)}
        bm_rank = sorted(bm_scores, key=lambda i: -bm_scores[i])
        bm_rr = {mid: 1.0 / (60 + r + 1) for r, mid in enumerate(bm_rank)}
        # semantic
        qv = self.embedder.embed(query)
        sem = self.index.search(qv, k=min(200, len(ids)))
        sem_rr = {mid: 1.0 / (60 + r + 1)
                  for r, (mid, _s) in enumerate(sem)
                  if mid in by_id}
        # RRF fuse
        fused = {}
        for mid in by_id:
            fused[mid] = bm_rr.get(mid, 0.0) + sem_rr.get(mid, 0.0)
        # rerank: recency + salience (s_mean)
        if rerank:
            import time
            now = time.time()
            for mid in fused:
                m = by_id[mid]
                age = max(1.0, now - m.get("t", now))
                rec = 1.0 / (1.0 + math.log1p(age / 3600.0))
                sal = 1.0 + 0.1 * abs(m.get("s", 0.0))
                fused[mid] *= (0.7 + 0.3 * rec) * sal
        ranked = sorted(fused, key=lambda i: -fused[i])[:k]
        out = []
        for mid in ranked:
            m = dict(by_id[mid])
            m["score"] = round(fused[mid], 5)
            out.append(m)
        return out
