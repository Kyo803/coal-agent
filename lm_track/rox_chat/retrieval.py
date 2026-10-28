"""Local retrieval + two-stage STR trigger (measured spec implementation).

Stage 1 (free): draft span exists; fire candidate iff min token prob
  < theta1 (logits already paid for). S_t may widen, never narrow.
Stage 2 (bounded): 2 extra samples of the span; retrieve iff they
  disagree (discrete semantic-entropy family).
Index: tiny BM25 over caller-supplied docs (local, no network). At 500M
  scale swap in a vector index; trigger logic is unchanged.
Fallbacks preserved: miss -> honest-uncertainty text; index down ->
  unverified flag. Both are inference-pipeline behaviors, not model magic.
"""
import math
import re
from collections import Counter


STOP = frozenset(
    "a an the is are was were be been to of in on for and or what who "
    "where when which how many much do does did tell me about it this that "
    "it s t".split())


def toks(s):
    return [t for t in re.findall(r"[a-z0-9]+", s.lower())
            if t not in STOP]


class BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.docs = docs
        self.td = [Counter(toks(d)) for d in docs]
        self.dl = [sum(c.values()) for c in self.td]
        self.avg = sum(self.dl) / max(1, len(self.dl))
        df = Counter()
        for c in self.td:
            for t in c:
                df[t] += 1
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5))
                    for t, f in df.items()}
        self.k1, self.b = k1, b
        self.down = False  # drill flag: simulate index outage

    def search(self, query, top=2):
        if self.down:
            return []
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
                s += self.idf.get(t, 0) * f * num / den
            out.append((s, i))
        out.sort(reverse=True)
        return [(self.docs[i], s) for s, i in out[:top] if s > 0]


def stage1_candidate(min_prob, theta1=0.7, s_widen=False):
    return (min_prob < theta1) or s_widen


def stage2_disagree(draft_norm, samples_norm):
    votes = [draft_norm] + list(samples_norm)
    top = max(set(votes), key=votes.count)
    return 1.0 - votes.count(top) / len(votes)


def str_answer(question, draft_fn, index, theta1=0.7, dis_thr=0.5,
               always_retrieve=False, conf_floor=0.5, refuse_floor=0.3):
    """draft_fn(question) -> (draft_text, min_prob, norm, samples_norm).
    Returns dict with answer text + provenance flags for the UI/eval.
    Miss gradient (measured data: 9/12 wrong answers had min_prob < 0.3,
    all 12 < 0.5): confident -> answer flagged UNVERIFIED; middling ->
    answer flagged LOW-CONFIDENCE; clueless -> honest refusal."""
    draft, minp, dn, sn = draft_fn(question)
    if index.down:
        return {"text": draft + " [unverified — index unavailable]",
                "status": "index-down", "retrieved": []}
    if always_retrieve or (stage1_candidate(minp, theta1)
                           and stage2_disagree(dn, sn) >= dis_thr):
        hits = index.search(question + " " + draft)
        if not hits:
            if minp >= conf_floor:
                return {"text": draft + " [unverified — nothing "
                                "relevant retrieved]",
                        "status": "unverified", "retrieved": []}
            if minp >= refuse_floor:
                return {"text": draft + " [unverified, low confidence — "
                                "nothing relevant retrieved]",
                        "status": "unverified-low", "retrieved": []}
            return {"text": "I don't have verified information on that.",
                    "status": "retrieval-miss", "retrieved": []}
        ctx = " ".join(h[0] for h in hits)
        return {"text": f"Based on retrieved context: {ctx} "
                        f"So: {draft} [sourced]",
                "status": "retrieved", "retrieved": [h[0] for h in hits]}
    return {"text": draft, "status": "direct", "retrieved": []}
