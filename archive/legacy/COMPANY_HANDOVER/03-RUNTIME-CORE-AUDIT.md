# 03 — RUNTIME CORE AUDIT (every file, what it is, what's in it)

This document covers the **root-level runtime modules** of the assistant. Each
entry: purpose → key contents/functions → relationships → how to run/test.

---

## `coal.py` (67 KB) — THE ENTRY POINT · unified assistant + CLI
The whole product in one file: the `Coal` class holds config, server manager,
session, memory, RAG, personality, router, permission system, executor, project
hooks.
- `Coal.__init__` wires everything; `respond()` is the full turn pipeline
  (see `02-ARCHITECTURE.md §2`).
- **Intent-first path:** forced tools for `write_file`, `remember`,
  `project_new`, `generate_image`/`edit_image`/`custom_image`,
  `ask_about_image`/`ocr_image`, `build_project`.
- **Write path:** `_gen_file`-style content-only pass, then Coal executes
  `write_file` with a confirmed path; `_langpack_context` injects the matching
  language pack; `_infer_filename`/`_extract_file_body` handle naming + body.
- **Autonomous builder:** `build_project`, `_plan_project`, `_gen_file`,
  `_verify_and_repair`, `_finish_project`, `_relax_tsconfig`,
  `_missing_modules`, `_related_files`, `_project_rel`, `_repair_instruction`,
  `_patch_file_section`, `_patch_budget`.
- **CLI:** `--say`, `--status`, `--session`, `--no-autostart`,
  `--show-thinking`, `--resume <name>`, `--finish <name>`. Reconfigures
  stdout/stderr to UTF-8 (Windows cp1252 would crash on model output).
- Run: `python coal.py`. Test: `python test_tools.py`, `python test_build.py`.

## `coal_config.py` (4.5 KB) — configuration loader
Loads `config.json` from the install dir; `cfg` singleton with sections
`model`, `fallback_servers`, `memory`, `personality`, `tools`, `image`,
`project`, `rag`. Everything reads config through here — never hard-code
paths/settings in handlers.

## `server_manager.py` (7.8 KB) — model server lifecycle
Owns the llama-server process: `ensure()` auto-starts if not running,
`is_running()` (duplicate-server guard — a real past bug), health check,
RAM/VRAM guard, Vulkan auto-tune (`gpu_layers` steps down on OOM), stop/status.
Also provides `status()` data used by `coal.py --status`.

## `coal_backend.py` (8.3 KB) — local model backend
OpenAI-compatible client for the local llama-server (`/v1/chat/completions`,
`/v1/models`). Class `CoalBackend`. Used by `streaming.py`/`generate.py`.
Rebranded from `qwen_backend.py` (class renamed too).

## `coal_template.py` (5.9 KB) — chat template + tool-call format
`build_chat` (exact Qwen chat template with `enable_thinking`), `split_thinking`
(separates `thinking`/`response` regions), `parse_tool_calls` (XML tool calls),
`TOOL_SCHEMAS`. Rebranded from `qwen_template.py`.

## `streaming.py` (5.5 KB) — live token streaming (SSE)
`stream_chat(messages, …, on_token, on_thinking, max_tokens, tool_choice)`:
SSE client that prints tokens live, splits thinking from the answer, normalizes
tool calls, and falls back to XML tool-call parsing. Returns
`(content, tool_calls, thinking)`.

## `session.py` (4.8 KB) — sessions
`Session.resume/latest/save/export` — conversations persist under `~/.coal/
sessions/`. Named sessions via `--session work`.

## `personality.py` (5.7 KB) — adaptive personality
`Personality` learns from how you talk: trait adjustment, `system_prompt()`
builds the adapted system prompt (name, traits, style rules). Persists to
`~/.coal/personality.json`.

## `router.py` (3.1 KB) — task router + thinking controller
Classifies the turn's kind (chat, code, tool, image, project, …), picks the
tool category to load, model tier, and the thinking flag.

## `attachments.py` (5.8 KB) — inference attachments (safety + math)
- `lockout_check(text)` — crisis-phrase safety, hard redirect (F1 1.0 on
  50K cases).
- `tool_gate(text)` — exact arithmetic gate (100% on 100K cases).
- Also holds the TME turn-memory helper. Docstring calls these "TME turn
  memory, tool gate, safety lockout".

## `observability.py` (3.1 KB) — logs + metrics
Structured logs, latency per stage, memory + tool traces. Used by the runtime
to give `--status` and diagnostics.

## `vision.py` (3.2 KB) — image input
Sends an image (path) to the local model via the mmproj vision tower;
`ask_about_image()` returns a description. Backs `ask_about_image` /
`ocr_image` tools.

## `rag.py` (6.4 KB) — document RAG
`RAG(root)` — `ingest_text(text, source)`, `search(query)`, `context(query)`
for the prompt. Index lives under `~/.coal/rag/`. Used by `ingest_docs` /
`search_docs` handlers (`tools/handlers_rag.py`).

## `retrieval.py` (4.1 KB) — retrieval + two-stage STR trigger
BM25-style local retrieval and the two-stage STR (surprise-triggered
retrieval) gate. Deterministic, no model. Measured spec in `str_config.json`.

## `bigindex.py` (4.1 KB) + `bigindex/` — corpus-backed retrieval
Inverted BM25 index over real corpus passages (`bigindex/passages.jsonl`,
`bigindex/index.pkl`). Bigger retrieval scale than `retrieval.py`.

## `resources.py` (8.2 KB) — image-gen resource swap coordinator
`swap_for_image` / `swap_for_edit`: park the 35B (kill llama-server, free
RAM+VRAM) → run `sd-cli` (FLUX.2 klein 4B, Vulkan) → reload the 35B.
Coordinates with `server_manager`. See `BACKLOG.md` for the sd-cli
flags (`. -r` ref edit, `. -i` init restyle).

## `langpacks.py` (11.2 KB) — language packs (P1)
Curated cheatsheets for TypeScript/React/Tailwind/Vite/Verilog under
`~/.coal/langpacks/<tech>/cheatsheet.md`. `install_curated()`, `list_packs()`,
`ingest_all()`. The write path injects the matching pack per file type
(`coal.py:_langpack_context`).

## `generate.py` (2.5 KB) — streaming generation over CoalChat
Streaming generation with the shared surprise signal (research-track helper
for the training side).

## `fallbacks.py` (2.6 KB) — Fallback Enforcer (resilience)
PLAN §7 as executable code: 5 fallback rows + drills (retrieval down, tool
error, model down, …).

## `lambda_governor.py` (3.1 KB) — EME hysteresis control
Closed-loop EME hysteresis (MoE-collapse escape). CPU-verified; used in the
training track, not the runtime hot path.

## `matrix.py` (3.5 KB) — interaction-matrix runner
Pairwise mechanism ablation at small scale (results in `matrix.json`).

## `muon.py` (5.4 KB) — optimizer
Muon (Liu et al. 2025) + AdamW hybrid. Training track.

## `fim.py` (6 KB) — Fast Interaction Matrix
Gradient-conflict screening between mechanisms. Offline analysis (results in
`fim.json`); never in the training loop.

## `latency.py` (2.3 KB) — latency accountant
Per-token stage budget with shedding. Training/inference accounting.

## `parity.py` (3 KB) — parity sentinel
Keeps FOU (fast/fixed optimizer) training approximation honest vs full
inference. CPU-verified.

## `rental_guardian.py` (3.3 KB) — rental watchdog
Preflight gates + in-run watchdog for rented GPUs ($ burn tracking, ckpt every
30 min). Training track.

## `calibrate.py` (2 KB) — STR calibrator
Freezes retrieval thresholds per model scale (θ1/dis from measured data →
`str_config.json`).

## `hf_backend.py` (4.5 KB) — HF instruct backend
HuggingFace `transformers` fallback backend ("a real talking brain behind our
deterministic layer"). Used by `run_local.py --backend hf`.

## `local_run.py` (5.7 KB) — single local entry point
Auto-detects the server + best model, `--selftest` tiers RAM, `--backend`
override (coal/ollama/hf/v2). See `LOCAL_RUN.md`.

## `run_local.py` (3.6 KB) — Coal local runtime launcher
Loads Coal on a desktop (RAM + optional small GPU). The documented "talk to
Coal" command in `LOCAL_RUN.md`.

## `install.py` (5.9 KB) — installer
Links model + server into `Program Files\Coal`, writes `config.json`,
`--check` verifies. First-run step.

## `personality.py`, `session.py`, `vision.py` — see above (already covered).

---

### `start_coal_server.bat` (0.4 KB) — server launcher
`cmd /c "start /b start_coal_server.bat"` starts llama-server detached with the
35B model. Manual start path; `server_manager.ensure()` does this automatically
too.

## Top-level docs (read these)

| File | What it is |
|------|-----------|
| `OVERVIEW.md` (12.2 KB) | **The master system doc** — install, run, capabilities, turn flow, tools table, memory, Vulkan, performance. Start here for product understanding. |
| `EVALUATION.md` (10.2 KB) | The evaluation report (see `06-…`). |
| `TRAINING_PLAN.md` | The training build plan (see `07-…`). |
| `LOCAL_RUN.md` | Local run guide (see `07-…`). |
| `BACKLOG.md` | Roadmap + captured notes (image editing, pending items, current state). |
| `eval_report.md` | Quick-scale eval report (see `06-…`). |

---

_Next: `04-TOOLS-LAYER-AUDIT.md`._