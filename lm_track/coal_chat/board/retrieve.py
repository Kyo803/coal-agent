"""Board retrieval: turn a query into a compact, provenance-aware board
card for the prompt.

Pipeline:
  query -> FTS5 (keyword) + vector (semantic) + entity-name match
        -> merge/rank candidates (relevance x salience x recency)
        -> graph expansion (1-2 hops over edges)
        -> render a compact card within a token budget

The full provenance (Coal's thinking) is NOT dumped here — it stays on
disk and is fetched on demand via board_show. The card carries the gist.
"""
from __future__ import annotations

import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from board.cache import HotCache

STOP = set("a an the is are was were be been to of in on for and or it this "
           "that i you he she we they my your what who where when how do does "
           "did about with me".split())


def _toks(s):
    return [t for t in re.findall(r"[a-z0-9]+", (s or "").lower())
            if t not in STOP and len(t) > 1]


class BoardRetriever:
    def __init__(self, board, embedder, index, cache=None):
        self.board = board
        self.embedder = embedder
        self.index = index
        self.cache = cache or HotCache(board)

    def retrieve(self, query, k_nodes=6, k_dossiers=4, hops=1):
        q = (query or "").strip()
        node_scores = {}
        dossier_scores = {}

        # 1. FTS keyword hits
        for hit in self.board.search_text(q, limit=12):
            if hit["card_type"] == "dossier":
                dossier_scores[hit["card_id"]] = \
                    dossier_scores.get(hit["card_id"], 0) + 1.0
            elif hit["card_type"] == "node":
                node_scores[hit["card_id"]] = \
                    node_scores.get(hit["card_id"], 0) + 1.0

        # 2. semantic hits
        if self.embedder is not None and self.index is not None:
            try:
                qv = self.embedder.embed(q)
                for nid, sim in self.index.search(qv, k=10, kind="node"):
                    node_scores[nid] = node_scores.get(nid, 0) + 1.5 * sim
                for did, sim in self.index.search(qv, k=6, kind="dossier"):
                    dossier_scores[did] = \
                        dossier_scores.get(did, 0) + 1.5 * sim
            except Exception:
                pass

        # 3. entity-name match
        toks = set(_toks(q))
        for n in self.board.top_nodes(limit=200):
            name_toks = set(_toks(n["name"]))
            if name_toks & toks:
                node_scores[n["id"]] = node_scores.get(n["id"], 0) + 1.2

        # 4. rank nodes (salience + recency)
        now = time.time()

        def nscore(nid):
            n = self.cache.node(nid)
            if not n:
                return -1
            sal = math.log1p(max(0.0, n.get("salience") or 0.0))
            age_h = max(1.0, (now - (n.get("last_seen") or now)) / 3600.0)
            rec = 1.0 / (1.0 + math.log1p(age_h / 24.0))
            return node_scores[nid] * (1.0 + 0.2 * sal) * (0.7 + 0.3 * rec)

        top_nodes = sorted(node_scores, key=nscore, reverse=True)[:k_nodes]
        top_nodes = [nid for nid in top_nodes if nscore(nid) > 0]

        # 5. graph expansion
        edges = []
        expanded = list(top_nodes)
        for nid in list(top_nodes):
            for nb in self.cache.neighbors(nid)[:8]:
                edges.append({"src": nid, "dst": nb["node_id"],
                              "relation": nb["relation"],
                              "name": nb["name"], "kind": nb["kind"],
                              "dir": nb["dir"]})
                if nb["node_id"] not in expanded:
                    expanded.append(nb["node_id"])

        # 6. rank dossiers
        top_dossiers = sorted(dossier_scores,
                              key=lambda d: -dossier_scores[d])[:k_dossiers]

        nodes = [self.cache.node(nid) for nid in expanded]
        nodes = [n for n in nodes if n]
        dossiers = []
        for did in top_dossiers:
            d = self._dossier_by_id(did)
            if d:
                dossiers.append(d)
        return {"nodes": nodes, "dossiers": dossiers, "edges": edges}

    def _dossier_by_id(self, did):
        r = self.board.conn.execute(
            "SELECT session_id FROM dossiers WHERE id=?", (did,)).fetchone()
        return self.board.get_dossier(r[0]) if r else None

    # ---- render ----
    def card(self, query, budget_tokens=700):
        res = self.retrieve(query)
        if not res["nodes"] and not res["dossiers"]:
            return ""
        budget_chars = budget_tokens * 4
        lines = []
        used = 0

        def add(line):
            nonlocal used
            if used + len(line) + 1 > budget_chars:
                return False
            lines.append(line)
            used += len(line) + 1
            return True

        if res["nodes"]:
            add("Known entities:")
            by_id = {n["id"]: n for n in res["nodes"]}
            for n in res["nodes"][:8]:
                if not add(f"- [{n['kind']}] {n['name']}"
                           + (f": {n['summary'][:80]}" if n.get("summary")
                              else "")):
                    break
            # relation lines for the top node(s)
            for e in res["edges"][:10]:
                src = by_id.get(e["src"])
                dst = by_id.get(e["dst"])
                if not src:
                    continue
                if e["dir"] == "out" and dst:
                    if not add(f"  {src['name']} --{e['relation']}--> "
                               f"{e['name']}"):
                        break
        if res["dossiers"]:
            add("Relevant conversations:")
            for d in res["dossiers"][:4]:
                title = d.get("title") or f"session {d.get('session_id')}"
                bits = []
                if d.get("decisions"):
                    bits.append("decisions: " + "; ".join(
                        str(x)[:60] for x in d["decisions"][:3]))
                if d.get("tasks"):
                    bits.append("tasks: " + "; ".join(
                        str(x)[:60] for x in d["tasks"][:3]))
                if not add(f"- {title}: {(d.get('summary') or '')[:140]}"
                           + (f" ({'; '.join(bits)})" if bits else "")):
                    break
        if not lines:
            return ""
        return "### board\n" + "\n".join(lines)


if __name__ == "__main__":
    import os
    import tempfile
    from board.store import BoardStore
    from board.builder import build_card
    d = tempfile.mkdtemp()
    st = BoardStore(os.path.join(d, "b.db"))
    build_card(st, None, None, {
        "session_id": 1, "msg_id": 1,
        "user_text": "building a robot arm", "thinking": "hardware",
        "output": "ok"}, {
        "title": "Robot arm kickoff",
        "summary": "started a robot arm with NEMA 23 motors",
        "topics": ["robotics"], "entities": [
            {"name": "robot arm", "kind": "project"},
            {"name": "NEMA 23", "kind": "tool"}],
        "relations": [{"src": "robot arm", "dst": "NEMA 23",
                       "relation": "uses"}],
        "facts": [], "decisions": ["use NEMA 23"], "tasks": ["pick driver"],
        "questions": [], "confidence": 0.9})
    r = BoardRetriever(st, None, None)
    print(r.card("what motors does the robot arm use?"))
    assert "NEMA 23" in r.card("robot arm")
    print("[board.retrieve] OK")
