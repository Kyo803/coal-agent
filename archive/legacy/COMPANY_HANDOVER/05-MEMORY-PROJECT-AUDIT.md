# 05 — MEMORY + PROJECT AWARENESS AUDIT (`memory/`, `project/`)

Two of the "forever memory" pillars. Every file documented.

---

## `memory/` — persistent local memory (no cloud)

Storage root: `~/.coal/` → `memory.db` (SQLite), `vectors/` (nomic-embed-text
768-d), `profile.json`, `personality.json`, `rag/`, `sessions/`.

| File | Purpose | Key contents |
|------|---------|--------------|
| `memory/__init__.py` (2.8 KB) | Package facade | Exports `Memory`, `MemoryTools`, `RAG`-wired root; the "no cloud, no network, all on disk" contract. |
| `memory/store.py` (6.8 KB) | SQLite store | Tables for sessions, messages, facts, entities, summaries. Read/write/delete + `all_facts()`. |
| `memory/embed.py` (6.4 KB) | Local embeddings | **CPU-only Ollama** (`nomic-embed-text` 768-d) via `ensure_ollama()` (starts Ollama on demand, `OLLAMA_VULKAN=0`). Falls back to in-process TF-IDF if Ollama is evicted. **Why CPU-only:** a GPU-loaded Ollama stole VRAM from the 35B and caused empty replies — a major past bug. |
| `memory/index.py` (3.5 KB) | Vector index | Numpy brute-force cosine (exact). **Self-heals dimension mismatch** (a past crash bug when embedding dims changed). |
| `memory/retrieve.py` (3.2 KB) | Hybrid retrieval | BM25 (keyword) + vector (semantic) fused. |
| `memory/consolidate.py` (6.4 KB) | Consolidation | Extracts durable facts from conversation + summarizes sessions. |
| `memory/profile.py` (2.5 KB) | User profile | Small, always in the prompt; both sides (what Coal knows, what to ask). |
| `memory/tools.py` (3 KB) | Model-callable tools | `remember`, `search_memory`, `memory_write`, `forget`, `update_profile` — the model learns (in SFT) to emit these; handled natively by `coal.py`. |
| `memory/assemble.py` (4.4 KB) | Context assembly | Builds the memory block of the prompt within a token budget (profile + facts + recent turns). |

**Gate:** `python test_memory.py` — a fact must survive a *new* session.

## `project/` — project awareness (multi-file coding without hallucination)

Projects live at `Desktop\Coal Projects\<name>\`; the ledger stays in
`~/.coal/projects\<name>\`.

| File | Purpose | Key contents |
|------|---------|--------------|
| `project/__init__.py` (0.5 KB) | Package marker | Declares the project-awareness contract. |
| `project/project.py` (12.2 KB) | Project model | `Project.open(name)` (creates Desktop folder + SQLite ledger), `scan()` (hash-tracks every file), `architecture()` (tree/symbols/imports), change detection. `slugify()`. |
| `project/journal.py` (3.7 KB) | Change journal | Append-only JSONL: every write/edit/delete/rename recorded automatically (hooks in file tools). `history(file)`, `summary()`, `by_file()`. |
| `project/audit.py` (6.3 KB) | Consistency audit | Missing imports (stdlib + common third-party aware), duplicate symbols, TODO/FIXME, orphaned files. `Auditor(p).audit()`. |
| `project/context.py` (3.8 KB) | Anti-hallucination context | Budget-aware prompt blocks: `file_context(path)` (content + symbols + imports + journal + related), `project_context()` (architecture overview). |

**Tools:** 8 project tools in `tools/handlers_project.py`; auto-journal hooks in
`tools/handlers_fs.py`.

## `project/contract.py` — spec-first interface contract (chip/RTL)

`project/contract.py` (`Contract` class) stores a per-project interface
contract (`~/.coal/projects/<name>/contract.json`): each HDL module's planned
ports. `coal.py` builds it via `chip_architect.ChipArchitect` before writing
files, injects the module's required ports into every `.v` write, and
`_verify_and_repair` checks written ports against it deterministically
(`[contract]` conformance). `chip_architect.py` drives `chip-design-ai-v4`
(3B) for `plan_ports` / `review`. **Verified:** generated ALU/regfile matched
their contract ports exactly; full multi-module CPU convergence still hits the
35B ceiling (testbench↔cpu_top drift), but the contract is the mechanism that
prevents interface drift.

## `board/` — the detective board (structured memory + provenance)

A derived, provenance-rich knowledge layer built from conversations. Separate
`~/.coal/board.db` (the raw log stays in `memory.db`; the board is rebuildable).

| File | Purpose | Key contents |
|------|---------|--------------|
| `board/__init__.py` (1 KB) | Package marker | Exports `BoardStore`; describes the layer. |
| `board/store.py` (16 KB) | Board store | SQLite schema + CRUD: `nodes`, `aliases`, `edges`, `dossiers`, `events`, `provenance`, `node_mentions`, `board_fts` (FTS5). `norm_key()`. |
| `board/queue.py` (2.2 KB) | Exchange queue | Append-only JSONL (`~/.coal/board_queue.jsonl`): `enqueue/pending/remove/count`. |
| `board/archivist.py` (7.7 KB) | The archivist | `coaln-3b` via Ollama; structured-JSON extraction; parks/reloads the 35B; `run()` batch; `extract()` one exchange. |
| `board/resolve.py` (1.4 KB) | Entity resolution | canonical → alias → (opt-in) embedding merge → new node. Conservative. |
| `board/builder.py` (5.8 KB) | Card builder | extraction → nodes/edges/dossier/events/FTS/embeddings + **provenance** (full thinking). |
| `board/retrieve.py` (7.3 KB) | Retrieval | FTS5 + vectors + entity match → graph expansion → compact `card()` for the prompt. |
| `board/cache.py` (2.2 KB) | RAM hot-graph | Bounded LRU over node/neighbor lookups (disk fallback). |
| `board/export.py` (3.2 KB) | Openable cards | `node_card`/`dossier_card`/`write_json` — cards incl. Coal's reasoning. |
| `board/ui.py` (3.2 KB) | Board UI server | Tiny local HTTP server: `/` serves `ui.html`, `/api/board` serves JSON. `serve()`. |
| `board/ui.html` (9 KB) | Board UI page | Flat, **solid-color only** (no gradients/images). Corkboard with red strings/pins. **Multi-select** (click/ctrl/marquee/Ctrl+A), **group move**, **zoom/pan**, **align/distribute**, **group boxes**, **notes**, **custom strings**, **color tags**, **lock**, **z-order**, **snap-to-grid**, **fit/reset**. Arrangement persists in localStorage and survives the 15s auto-refresh. |

**Wiring:** `coal.py` (`_init_board`, `_board_card`, `board_enqueue`,
`board_tick`, `_board_forget`), `memory/assemble.py` (a `board` tier),
`memory/store.py` (`thinking` column), `tools/handlers_board.py`, `--archive`
and `--board-export` CLI. Tests: `test_board.py` (31 checks).

---

_Next: `06-EVAL-TESTING-AUDIT.md`._