"""Conservative entity resolution for the board.

Order (safest first):
  1. exact canonical match
  2. known alias
  3. (optional, off by default) embedding-similarity merge above a HIGH
     threshold — a wrong merge is worse than a missed one, so this is
     gated by config and reversible (we only add an alias, never delete).
  4. create a new node
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from board.store import norm_key


def resolve_node(board, name, kind="concept", embedder=None, index=None,
                 merge_threshold=0.0):
    name = (name or "").strip()
    if not name:
        return None
    # 1. canonical
    n = board.get_node(name)
    if n:
        board.upsert_node(n.get("kind") or kind, name, salience=1.0)
        return n["id"]
    # 2. alias
    aid = board.find_alias(name)
    if aid:
        board.upsert_node(kind, name, salience=1.0)
        return aid
    # 3. embedding merge (opt-in, high threshold)
    if embedder is not None and index is not None and merge_threshold > 0:
        try:
            v = embedder.embed(name)
            hits = index.search(v, k=1, kind="node")
            if hits and hits[0][1] >= merge_threshold:
                nid = hits[0][0]
                board.add_alias(nid, name)
                return nid
        except Exception:
            pass
    # 4. new node
    return board.upsert_node(kind, name, salience=1.0)
