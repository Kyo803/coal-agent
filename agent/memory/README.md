# memory — recall across sessions

Persistent memory under `~/.coal` (SQLite + embeddings).

- `store.py` — turns, facts, sessions.
- `embed.py` — Ollama embeddings (`nomic-embed-text`).
- `index.py`, `retrieve.py` — vector + keyword recall.
- `assemble.py` — builds the per-turn context.
- `consolidate.py` — extracts durable facts from conversations.
- `profile.py`, `mediator.py` — user profile and conflict handling.
