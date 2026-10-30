"""Bridge: write learning outcomes onto Coal's detective board.

Each studied topic becomes a concept node with its mastery as salience,
plus learning/source events on the timeline — so autonomous learning shows
up in the brain's structured memory.
"""
from __future__ import annotations

import os

from coal_config import cfg


def record_cycle(topic: str, mastery: float = 0.0, summary: str = "",
                 sources: list | None = None) -> bool:
    try:
        from board.store import BoardStore
        db = os.path.join(cfg.memory_root, "board.db")
        st = BoardStore(db)
        try:
            nid = st.upsert_node("concept", topic,
                                 summary=(summary or "")[:400],
                                 salience=float(mastery or 0.0))
        except TypeError:
            nid = st.upsert_node("concept", topic)
        st.add_event("learning",
                     f"studied {topic} (mastery {round(float(mastery or 0), 3)})",
                     node_id=nid)
        for s in (sources or [])[:3]:
            st.add_event("source", str(s)[:200], node_id=nid)
        st.close()
        return True
    except Exception:
        return False
