# board — the project board

Every exchange can be archived into a "detective board": cards with
provenance, linked by edges.

- `archivist.py` — small local model that extracts cards from a turn.
- `queue.py` — pending exchanges, processed in the background.
- `store.py`, `retrieve.py`, `resolve.py` — cards, search, dedupe.
- `builder.py`, `export.py`, `cache.py` — assembly and export.
- `ui.py` — local web view (start with `scripts/board_ui.bat`).
