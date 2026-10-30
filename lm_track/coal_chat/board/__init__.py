"""Coal Board — the "detective board" of structured, provenance-rich
knowledge derived from conversations.

The board is a *derived* intelligence layer: it is built from the raw
conversation log (memory.db) by the archivist model, and can be rebuilt
at any time without touching the raw history.

Layers:
  board/store.py      SQLite schema + CRUD (nodes, aliases, edges,
                      dossiers, events, provenance, FTS5)
  board/queue.py      per-turn exchange queue (what to archive)
  board/archivist.py  the small model that writes the board (coaln-3b)
  board/resolve.py    conservative entity resolution
  board/builder.py    queue -> cards + provenance
  board/retrieve.py   multi-hop retrieval into a prompt card
  board/cache.py      RAM hot-graph cache
  board/export.py     openable JSON cards

Storage lives at ~/.coal/board.db (separate from memory.db so the raw
record is never risked by board schema changes / rebuilds).
"""
from .store import BoardStore  # noqa: F401

__all__ = ["BoardStore"]