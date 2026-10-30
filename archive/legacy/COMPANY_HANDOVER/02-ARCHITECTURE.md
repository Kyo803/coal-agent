# 02 — ARCHITECTURE (system design, turn flow, module relationships)

How the pieces fit together. Read `01-HOW-IT-WAS-BUILT.md` first for the
narrative; this is the technical map.

---

## 1. The runtime, at a glance

```
┌────────────────────────────────────────────────────────────────────┐
│  coal.py  (Coal class + CLI)                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ per turn: safety → calc → route → memory → rag → personality │  │
│  │ → INTENT-FIRST → lazy tools → stream → execute → store       │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────┬───────────────────────┬───────────────────────┬────────────┘
       │                       │                       │
  llama-server          tools/  (executor)          memory/ + project/
  (35B gguf,            specs/permissions/exec/     (SQLite + nomic      \
   127.0.0.1:1234)      shell_gate/intent/handlers   embeddings)          │
       │                                                              │
  coal_backend.py                                                   rag.py
  streaming.py                                                    vision.py
  coal_template.py                                                 resources.py
```

## 2. The turn flow (what `Coal.respond()` does)

1. **Safety** — `attachments.lockout_check(text)`: crisis phrase? hard
   redirect.
2. **Calculator** — `attachments.tool_gate(text)`: pure arithmetic? answered
   directly (100% on 100K cases).
3. **Router** — `router.py`: task kind → which tools are relevant + model +
   thinking flag.
4. **Memory assemble** — `memory/assemble.py`: profile + facts + past turns
   into the prompt, within a token budget.
5. **RAG retrieve** — `rag.py`: top document chunks.
6. **Personality** — `personality.py`: adapted system prompt.
7. **Intent-first** — `tools/intent.py`: detect purpose → force the specific
   tool (write_file, generate_image, build_project, etc.).
8. **Lazy tool schemas** — only the router-detected category's tools enter the
   prompt (capped ~30) + memory tools always.
9. **Stream** — `streaming.py` calls the server; `coal_template.py` splits
   thinking from the visible answer; content is captured even when it arrives
   on the reasoning channel.
10. **Execute tools** — native (memory/RAG) or `tools/exec.py` (fs/git/exec/
    web/db/browser), permission-gated.
11. **Store + consolidate** — facts extracted by the model, profile updated,
    session saved; consolidation every N turns.

## 3. The tool layer architecture

```
tools/specs.py       registry: 369 tools, 17 category groups, json-schema params
tools/permissions.py Tier 0 auto / Tier 1 confirm / Tier 2 disabled
tools/exec.py        ToolExecutor: permission gate + 90s timeout + result cap
tools/shell.py       run_safe: gate-then-run for free-text commands
tools/shell_gate.py  CMD + PowerShell tier tables + bypass defenses
tools/intent.py      purpose → tool + args + confidence (intent-first)
tools/handlers_*.py  fs, exec, other, misc, browser, db, web2, cloud,
                     image, project, rag, build, self  (implementations)
```

- **Lazy loading:** `lazy_schemas(ensure=…)` — only the needed category's
  tools are materialized into the prompt. Meta-tools (`list_tools`,
  `use_category`) are removed from prompts.
- **Native tools** (handled by `coal.py`, not the executor): memory tools +
  `build_project`.

## 4. Memory architecture (`memory/`)

```
store.py       SQLite: sessions, messages, facts, entities, summaries
embed.py       local embeddings (nomic-embed-text 768-d via CPU-only Ollama;
               falls back to in-process TF-IDF if Ollama is evicted)
index.py       numpy brute-force cosine vector index (dim self-heals)
retrieve.py    hybrid BM25 (keyword) + vector (semantic)
consolidate.py durable-fact extraction + session summarization
profile.py     user profile (always in the prompt)
tools.py       model-callable memory tools (remember/search_memory/…)
assemble.py    builds the prompt's memory block under a token budget
```

Storage root: `~/.coal/` (`memory.db`, `vectors/`, `profile.json`,
`personality.json`, `rag/`, `sessions/`). Delete `~/.coal` to wipe everything.

## 5. Project awareness (`project/`)

```
project.py  Project model: Desktop\Coal Projects\<name>\, SQLite ledger,
            architecture map (tree/symbols/imports), scan for changes
journal.py  append-only JSONL of every write/edit/delete (auto-hooked)
audit.py    missing imports, duplicate symbols, orphans, TODO markers
context.py  budget-aware prompt blocks (file_context / project_context)
```

## 6. The image resource swap

```
resources.py  swap_for_image / swap_for_edit:
              park 35B → sd-cli (FLUX.2 klein 4B, Vulkan) → reload 35B
tools/handlers_image.py  generate_image / edit_image / custom_image
```

Two heavy models cannot share 24 GB RAM, so they time-slice.

## 7. The autonomous builder (native in `coal.py`)

```
build_project(description)   → plan → write files → npm install →
                               tsconfig relax → audit → verify+repair
_plan_project                model returns a JSON file manifest (retries)
_gen_file                    one file with langpack + project context;
                             validates output, retries on truncation/echo
_verify_and_repair           run build; on failure regenerate the files
                             named in the compiler output (path-aware,
                             ANSI-safe, fence-safe, module-balance-aware)
_finish_project              no re-plan: install + verify + repair
```

## 8. Key data flows

- **Config:** `coal_config.py` reads install `config.json`; everything (model,
  memory, tools, image, project) is configured there.
- **Model talk:** `coal_backend.py` (OpenAI-compatible) or `hf_backend.py`
  (HF fallback) or Ollama fallback; `streaming.py` on top.
- **Observability:** `observability.py` records structured logs + latency +
  tool traces; `server_manager.py` writes server health/RAM/VRAM state.

## 9. What NOT to touch unless you know why

- `tools/handlers_cloud.py` Tier-2 stubs are intentionally honest — keep them.
- The `noUnusedLocals`/`noUnusedParameters` relaxation in `_relax_tsconfig`
  exists because generated code frequently leaves unused imports; it is what
  lets builds converge. Removing it will break the autonomous builder.
- `_clean_fences` / backtick-restoration in `tools/handlers_fs.py` are
  deliberate corrections for model output quirks — do not "simplify" them away.

---

_Next: `03-RUNTIME-CORE-AUDIT.md`._