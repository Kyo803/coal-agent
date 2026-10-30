"""Build an instruction dataset from what Coal has learned.

Sources: learning notes, board dossiers (if present), and synthesis
summaries. Output is chat-format JSONL suitable for QLoRA.
"""
from __future__ import annotations

import json
import os

from coal_config import cfg


def dir() -> str:
    p = os.path.join(cfg.memory_root, "finetune")
    os.makedirs(p, exist_ok=True)
    return p


def _pair(topic: str, text: str, kind: str = "explain") -> dict:
    prompts = {
        "explain": f"Explain {topic}.",
        "how": f"How does {topic} work?",
        "why": f"Why does {topic} matter?",
    }
    return {"messages": [
        {"role": "system", "content": "You are Coal, a precise local AI."},
        {"role": "user", "content": prompts.get(kind, prompts["explain"])},
        {"role": "assistant", "content": text[:4000]},
    ], "meta": {"topic": topic, "kind": kind}}


def from_notes(limit: int = 1000) -> list:
    from learning import notes
    out = []
    for r in notes.all_notes(limit=limit):
        text = (r.get("text") or "").strip()
        topic = (r.get("topic") or "").strip()
        if len(text) < 60 or not topic:
            continue
        out.append(_pair(topic, text,
                         "explain" if r.get("kind") != "synthesis" else "why"))
    return out


def from_board(limit: int = 500) -> list:
    """Board dossiers as Q/A pairs (best-effort)."""
    out = []
    try:
        from board.store import BoardStore
    except Exception:
        return out
    db = os.path.join(cfg.memory_root, "board.db")
    if not os.path.exists(db):
        return out
    try:
        st = BoardStore(db)
        rows = st.recent_events(limit=limit) if hasattr(st, "recent_events") \
            else []
        for row in rows:
            summary = str(row)
            out.append(_pair("recent work", summary, "why"))
        st.close()
    except Exception:
        return out
    return out


def build(limit: int = 1200) -> list:
    data = from_notes(limit) + from_board(limit // 2)
    # dedupe by assistant content
    seen, uniq = set(), []
    for d in data:
        key = d["messages"][-1]["content"][:200]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)
    return uniq[:limit]


def write(name: str = "dataset.jsonl", limit: int = 1200) -> dict:
    data = build(limit)
    p = os.path.join(dir(), name)
    with open(p, "w", encoding="utf-8") as f:
        for d in data:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return {"path": p, "count": len(data)}
