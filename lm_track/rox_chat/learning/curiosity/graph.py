"""Curiosity graph: topics, their mastery, and how they relate.

It is the map of what ROX N knows it knows, what it wants to know, and
what sits just past the edge (the *frontier*). The drive scores candidates
from here, and each learning cycle updates mastery/interest/visits and
adds edges between related topics.
"""
from __future__ import annotations

from .. import paths

_FILE = "curiosity.json"


def _key(a, b):
    a, b = sorted([str(a), str(b)])
    return f"{a}\t{b}"


class CuriosityGraph:
    def __init__(self, data=None):
        d = data or paths.load_json(_FILE, {}) or {}
        self.topics = d.get("topics", {})
        self.edges = d.get("edges", {})

    # ---- persistence ----
    def save(self):
        paths.save_json(_FILE, {"topics": self.topics, "edges": self.edges})

    # ---- topics ----
    def ensure(self, name, interest=0.5, parent=None):
        name = str(name).strip()
        if not name:
            return None
        t = self.topics.get(name)
        if t is None:
            t = {"interest": round(float(interest), 3), "visits": 0,
                 "mastery": 0.0, "last": None, "sources": [],
                 "questions": [], "notes": 0, "parents": []}
            if parent:
                t["parents"].append(parent)
            self.topics[name] = t
        elif parent and parent not in t["parents"]:
            t["parents"].append(parent)
        if parent:
            self.add_edge(parent, name, 1.0)
        return name

    def seed(self, topics, interest=0.6):
        added = 0
        for t in topics:
            if t not in self.topics:
                self.ensure(t, interest=interest)
                added += 1
        if added:
            self.save()
        return added

    def get(self, name):
        return self.topics.get(name)

    def touch(self, name, source=None, question=None, mastery_delta=0.0,
              interest_delta=0.0):
        self.ensure(name)
        t = self.topics.get(name)
        if t is None:
            return None
        t["visits"] = int(t.get("visits", 0)) + 1
        t["last"] = paths.now()
        t["mastery"] = max(0.0, min(1.0, float(t.get("mastery", 0))
                                     + float(mastery_delta)))
        t["interest"] = max(0.0, min(1.0, float(t.get("interest", 0.5))
                                      + float(interest_delta)))
        if source and source not in t["sources"]:
            t["sources"].append(source)
            t["sources"] = t["sources"][-50:]
        if question and question not in t["questions"]:
            t["questions"].append(question)
            t["questions"] = t["questions"][-50:]
        if mastery_delta > 0:
            t["notes"] = int(t.get("notes", 0)) + 1
        self.save()
        return t

    # ---- edges ----
    def add_edge(self, a, b, weight=1.0):
        if not a or not b or a == b:
            return
        k = _key(a, b)
        self.edges[k] = min(5.0, float(self.edges.get(k, 0.0)) + weight)

    def neighbors(self, name):
        out = []
        for k, w in self.edges.items():
            a, b = k.split("\t")
            if a == name:
                out.append((b, w))
            elif b == name:
                out.append((a, w))
        return sorted(out, key=lambda kv: -kv[1])

    # ---- frontier / candidates ----
    def frontier(self, n=20):
        """Topics worth learning next: high interest, low mastery, less
        visited ranks higher."""
        scored = []
        for name, t in self.topics.items():
            interest = float(t.get("interest", 0.5))
            mastery = float(t.get("mastery", 0.0))
            visits = int(t.get("visits", 0))
            # unexplored strongly favoured; repeated visits penalised
            score = interest * (1.0 - 0.7 * mastery) / (1.0 + 0.25 * visits)
            scored.append((name, round(score, 4)))
        scored.sort(key=lambda kv: -kv[1])
        return scored[:n]

    def children(self, name):
        return [c for c, _ in self.neighbors(name)
                if name in self.topics.get(c, {}).get("parents", [])]

    def stats(self):
        return {"topics": len(self.topics), "edges": len(self.edges),
                "frontier": [n for n, _ in self.frontier(5)]}
