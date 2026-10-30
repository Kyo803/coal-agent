"""Board export: build "openable" cards (JSON) that show, for any piece
of knowledge, what Coal thought when it learned it.

A card bundles:
  - the node/dossier itself
  - its relations / neighbors
  - the provenance: user text, Coal's FULL reasoning, Coal's reply,
    the archivist's notes and confidence
  - timeline events and mentions

This is the backend for the (later) visual detective board UI, and is
already useful from the CLI / tools.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def node_card(board, node_id, with_provenance=True):
    n = board.get_node_by_id(node_id)
    if not n:
        return None
    card = {
        "type": "node",
        "node": n,
        "neighbors": board.neighbors(node_id),
        "timeline": board.timeline(limit=10, node_id=node_id),
        "mentions": board.mentions_of(node_id),
    }
    if with_provenance:
        card["provenance"] = board.provenance_for("node", node_id)
    return card


def dossier_card(board, session_id, with_provenance=True):
    d = board.get_dossier(session_id)
    if not d:
        return None
    card = {"type": "dossier", "dossier": d}
    if with_provenance:
        card["provenance"] = board.provenance_for("dossier", d["id"])
    return card


def export_all(board, limit=200, with_provenance=True):
    """Every card on the board (nodes + dossiers) as a list."""
    out = []
    for n in board.top_nodes(limit=limit):
        out.append(node_card(board, n["id"], with_provenance))
    for d in board.recent_dossiers(limit=limit):
        out.append(dossier_card(board, d["session_id"], with_provenance))
    return out


def write_json(board, out_path, limit=200, with_provenance=True):
    cards = export_all(board, limit=limit, with_provenance=with_provenance)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"cards": cards}, f, indent=1, ensure_ascii=False)
    return out_path, len(cards)


if __name__ == "__main__":
    import tempfile
    from board.store import BoardStore
    from board.builder import build_card
    d = tempfile.mkdtemp()
    st = BoardStore(os.path.join(d, "b.db"))
    build_card(st, None, None, {
        "session_id": 1, "msg_id": 1, "user_text": "building a robot arm",
        "thinking": "user picked NEMA 23; remember the motor choice",
        "output": "nice"}, {
        "title": "Robot arm kickoff", "summary": "started arm",
        "topics": ["robotics"], "entities": [
            {"name": "robot arm", "kind": "project"},
            {"name": "NEMA 23", "kind": "tool"}],
        "relations": [{"src": "robot arm", "dst": "NEMA 23",
                       "relation": "uses"}],
        "facts": [], "decisions": ["use NEMA 23"], "tasks": [],
        "questions": [], "confidence": 0.9})
    out, n = write_json(st, os.path.join(d, "cards.json"))
    card = dossier_card(st, 1)
    print("[board.export] wrote", n, "cards ->", out)
    print("[board.export] thinking:", card["provenance"][0]["thinking"])
    assert card["provenance"][0]["thinking"].startswith("user picked")
    print("[board.export] OK")
