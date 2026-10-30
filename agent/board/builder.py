"""Builder: turn one archivist extraction into board cards + provenance.
Writes, for a single exchange:
  - entity nodes (+ mentions, + embeddings)
  - typed edges between them
  - the session dossier (topics/facts/decisions/tasks/questions/summary)
  - timeline events for decisions and tasks
  - FTS text for keyword recall
  - provenance: the user text, Coal's FULL thinking, Coal's reply,
    the archivist's notes and confidence — this is the "what Coal thought"
    record behind every card.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from board.store import norm_key
from board.resolve import resolve_node

def build_card(board, embedder, index, job, data,
               merge_threshold=0.0):
    session_id = job.get("session_id")
    msg_id = job.get("msg_id")
    user_text = job.get("user_text", "") or ""
    thinking = job.get("thinking", "") or ""
    output = job.get("output", "") or ""

    data = data or {}
    entities = data.get("entities") or []
    relations = data.get("relations") or []

    # 1. entities -> nodes
    name_to_id = {}
    for ent in entities[:60]:
        if not isinstance(ent, dict):
            continue
        name = (ent.get("name") or "").strip()
        kind = (ent.get("kind") or "concept").strip()
        if not name:
            continue
        nid = resolve_node(board, name, kind, embedder=embedder, index=index,
                           merge_threshold=merge_threshold)
        if not nid:
            continue
        name_to_id[norm_key(name)] = nid
        if msg_id is not None:
            board.add_mention(nid, msg_id, session_id)
        if embedder is not None and index is not None:
            try:
                v = embedder.embed(f"{name} ({kind})")
                index.add(nid, v, kind="node")
            except Exception:
                pass

    # 2. relations -> edges
    for rel in relations[:60]:
        if not isinstance(rel, dict):
            continue
        s = name_to_id.get(norm_key(rel.get("src", "")))
        d = name_to_id.get(norm_key(rel.get("dst", "")))
        if s and d:
            board.add_edge(s, d,
                           (rel.get("relation") or "related_to").strip()[:48],
                           source_msg=msg_id)

    # 3. dossier (per session)
    ent_names = [e.get("name") for e in entities
                 if isinstance(e, dict) and e.get("name")]
    board.upsert_dossier(
        session_id,
        title=(data.get("title") or "").strip(),
        topics=data.get("topics") or [],
        entities=ent_names,
        facts=data.get("facts") or [],
        decisions=data.get("decisions") or [],
        tasks=data.get("tasks") or [],
        questions=data.get("questions") or [],
        summary=(data.get("summary") or "").strip(),
    )

    # 4. timeline events
    for dec in (data.get("decisions") or [])[:12]:
        board.add_event("decision", str(dec)[:300], session_id=session_id,
                        msg_id=msg_id)
    for task in (data.get("tasks") or [])[:12]:
        board.add_event("task", str(task)[:300], session_id=session_id,
                        msg_id=msg_id)

    # 5. FTS text for the dossier
    txt = " ".join(
        [str(data.get("title", "")), str(data.get("summary", ""))]
        + [str(t) for t in (data.get("topics") or [])]
        + [str(f) for f in (data.get("facts") or [])]
        + [str(d) for d in (data.get("decisions") or [])]
        + ent_names
    )
    dossier = board.get_dossier(session_id) if session_id is not None else None
    if session_id is not None:
        board.index_text("dossier", session_id, txt)
        # embed the dossier for semantic recall
        if embedder is not None and index is not None and dossier:
            try:
                v = embedder.embed(txt[:1500] or str(session_id))
                index.add(dossier["id"], v, kind="dossier")
            except Exception:
                pass

    # 6. provenance — the "what Coal thought" record
    card_id = dossier["id"] if dossier else (session_id or 0)
    try:
        conf = float(data.get("confidence") or 0.0)
    except Exception:
        conf = 0.0
    board.add_provenance(
        "dossier", card_id, session_id=session_id, msg_id=msg_id,
        user_text=user_text, thinking=thinking, output=output,
        archivist_notes=(data.get("summary") or "").strip(),
        confidence=conf)

    return {"nodes": len(name_to_id), "dossier": session_id,
            "entities": ent_names}


if __name__ == "__main__":
    import os
    import tempfile
    from board.store import BoardStore

    d = tempfile.mkdtemp()
    st = BoardStore(os.path.join(d, "board.db"))
    job = {"session_id": 1, "msg_id": 7,
           "user_text": "I'm building a robot arm with NEMA 23 motors",
           "thinking": "hardware project; user picked steppers",
           "output": "Great — NEMA 23s work well with a 4A driver."}
    data = {
        "title": "Robot arm kickoff",
        "summary": "User started a robot arm project using NEMA 23 motors.",
        "topics": ["robotics", "motors"],
        "entities": [
            {"name": "robot arm", "kind": "project"},
            {"name": "NEMA 23", "kind": "tool"},
        ],
        "relations": [{"src": "robot arm", "dst": "NEMA 23",
                       "relation": "uses"}],
        "facts": ["user is building a robot arm"],
        "decisions": ["use NEMA 23 stepper motors"],
        "tasks": ["choose a driver board"],
        "questions": [],
        "confidence": 0.9,
    }
    out = build_card(st, None, None, job, data)
    print("[builder] built:", out)
    print("[builder] stats:", st.stats())
    print("[builder] neighbors:", st.neighbors(
        st.get_node("robot arm")["id"]))
    prov = st.provenance_for("dossier", 1)
    print("[builder] provenance thinking:", prov[0]["thinking"])
    assert prov[0]["thinking"] == job["thinking"]
    print("[builder] OK")
