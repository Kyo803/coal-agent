# 03 — Forever Memory (`memory/`)

## Purpose

ROX N "remembers everything" across sessions. Memory is five tiers
(CoALA/MemGPT-inspired), all local, all on disk under `~/.rox/`:

```
core      -> profile.json        (always in the prompt)
working   -> current session tail (verbatim)
episodic  -> past turns, semantic search
semantic  -> extracted facts/entities
knowledge -> user docs + domain data (RAG)
```

## Module map

| Module | Role |
|---|---|
| `store.py` | SQLite store: sessions, messages, facts, entities, summaries, profile |
| `embed.py` | Embedding backends (Ollama nomic → MiniLM → TF-IDF fallback) |
| `index.py` | Vector index (numpy brute-force cosine; FAISS if installed) |
| `retrieve.py` | Semantic retrieval over messages/facts |
| `consolidate.py` | Extract durable facts + entities from user self-disclosure |
| `profile.py` | User profile (key/value) |
| `assemble.py` | Build the prompt context within a token budget |
| `tools.py` | Model-callable memory tools (search_memory, remember, ...) |

## `store.py` — SQLite schema

Tables: `sessions`, `messages`, `facts`, `entities`, `summaries`,
`profile`. WAL mode, no network. Indexes on message session/created and
fact subject.

## `embed.py` — embeddings with graceful degradation

Priority:
1. **Ollama `nomic-embed-text`** (768-d) — real semantic embeddings
2. **sentence-transformers MiniLM** (384-d)
3. **hashed TF-IDF** (no deps, weak but always works)

**Critical design (from a real incident):**
Ollama runs **CPU-only** (`OLLAMA_VULKAN=0`, `OLLAMA_GPU=0`,
`OLLAMA_KEEP_ALIVE=0`) and is started **on demand** by `ensure_ollama()`.
This is because a GPU-loaded Ollama model was **stealing VRAM from the
35B**, causing empty replies. The embedder also self-heals: if Ollama
hiccups, `embed()` falls back to TF-IDF of the correct dim — never
returns a 0-length vector that crashes the index.

## `index.py` — vector index with self-healing

- Persists per-kind: `<kind>.npy` + `<kind>.ids.json`
- `add()` detects an **embedding-dimension change** (e.g. TF-IDF 384-d
  persisted, then nomic 768-d arrives) and **drops the stale vectors**
  rather than crashing — `np.vstack` on mismatched dims was a real crash.
- `search()` returns `[]` on dim mismatch (safe).

## `consolidate.py` — what makes "remembers everything" work

Runs every N turns / at session end. Deterministic regex patterns
extract facts from user self-disclosure:

```
"my name is X"          -> name
"I am a/an X"           -> is_a
"I work at/on X"        -> works_on
"I am building X"       -> builds
"I like/love X"         -> likes
"my dog/cat is X"       -> pet_name
"I live in X"           -> lives_in
"I am N years old"      -> age
"my project/company is X" -> project
"I use X"               -> uses
```

Plus entity extraction (Capitalized terms) and a model-based path
(`extract_facts_model`) that uses the 35B for richer extraction.

## `assemble.py` — budget-aware context

`build(query, session_id, budget_tokens=1500)` adds tiers greedily in
priority order and always keeps the working tail. Returns
`{text, tiers, tokens}`. This prevents the 8K context from flooding.

## Memory in action (verified)

- "my name is WERU and I build robot arms with NEMA 23 motors"
  → later "what motors do I use?" → **"NEMA 23 motors"**
- Fact consolidation → profile updates → personality absorbs facts
- Cross-session recall proven by `test_memory.py` and the 450K eval
  memory suite at 100%

## Data locations

| Path | Contents |
|---|---|
| `~/.rox/memory.db` | SQLite (sessions, messages, facts, entities) |
| `~/.rox/vectors/` | embedding vectors (`.npy`) + ids |
| `~/.rox/profile.json` | user profile |
| `~/.rox/personality.json` | adaptive traits |
| `~/.rox/sessions/` | session JSON files |
| `~/.rox/rag/` | RAG document index |
| `~/.rox/work/` | ROX workspace (created files, generated images) |
| `~/.rox/projects/` | project ledgers + journals |

Wipe `~/.rox` to reset everything.