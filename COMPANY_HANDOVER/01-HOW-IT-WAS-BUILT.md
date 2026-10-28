# 01 — HOW ROX N WAS BUILT (the story, decisions, and why)

This document is the narrative the next company needs before touching code: how
the system was built in phases, what each phase added, and the decisions that
are load-bearing. It is honest about what is proven and what is not.

---

## 1. The 12-step build (the foundation)

ROX N was built bottom-up in twelve steps. Each step produced something
verifiable before the next began:

1. **Config + install** — `rox_config.py` + `install.py` + the install dir
   under `Program Files\ROX N`. Single source of truth for model, server,
   memory, tools, image settings.
2. **Model server** — llama.cpp `llama-server` serving the 35B GGUF on
   `127.0.0.1:1234`; `server_manager.py` owns start/stop/health/RAM-guard.
3. **Chat template + streaming** — `rox_template.py` (exact Qwen chat
   template, thinking split, tool-call XML) + `streaming.py` (SSE client).
4. **Chat loop** — `chat.py`/`chat_v2.py`/`rox.py` turn loop:
   safety → calc → route → memory → rag → personality → stream → tools → store.
5. **Memory** — `memory/` package: SQLite store, local embeddings, vector
   index, hybrid retrieve, consolidate, profile, model-callable tools,
   context assembly. Proven at 100% on 50,000 recall cases.
6. **Personality** — `personality.py` (adaptive, learns from how you talk).
7. **Sessions** — `session.py` (save/resume/list/export).
8. **Vision** — `vision.py` (mmproj) + `ask_about_image`/`ocr_image`.
9. **RAG** — `rag.py` document ingest + retrieve.
10. **Safety + math** — `attachments.py`: `lockout_check` (crisis) +
    `tool_gate` (calculator).
11. **Router** — `router.py` (task kind + model + thinking flag).
12. **Observability** — `observability.py` (structured logs, latency,
    memory + tool traces).

**Vulkan milestone (later):** swapped the server binary to llama.cpp 2.46.0
Vulkan, `gpu_layers: 8`. Tokens/sec stayed ~equal (RX 570 is old) but free RAM
went from ~0.5 GB to ~9-10 GB — the headroom that keeps Ollama embeddings alive
beside the brain. `server_manager` auto-steps `gpu_layers` down on VRAM OOM.

## 2. The tool layer

- `tools/specs.py` — registry, **369 tools / 17 category groups** (see
  `04-…` for the exact category table). Lazy-loads only the router-detected
  category per turn (capped ~30), memory tools always present.
- `tools/permissions.py` — Tier 0 auto · Tier 1 ask-confirm · Tier 2 disabled
  by default.
- `tools/exec.py` — safe executor: permission gate, 90 s timeout, result cap.
- `tools/shell_gate.py` + `tools/shell.py` — the only path free-text commands
  run through. CMD + PowerShell tier tables (T0 read auto, T1 project-dev
  auto, T2 elevated ask, T3 never) + bypass defenses (chaining, wrappers,
  aliases, indirect exec, path traversal, piping-to-execution).
- `tools/intent.py` — **intent-first calling**: reads *what you want*, then
  forces the specific tool. High-confidence intents bypass model tool-call
  unreliability (the write path captures the model's reasoning channel as file
  content).

## 3. Project awareness (multi-file coding without hallucination)

`project/` package: `project.py` (file ledger + architecture map), `journal.py`
(append-only JSONL change log, auto-hooked into every file tool), `audit.py`
(missing imports, duplicates, orphans, TODOs), `context.py` (budget-aware
anti-hallucination prompt blocks). Projects live on the Desktop under
`ROX Projects\<name>\`; the ledger stays clean in `~/.rox/projects\<name>\`.

## 4. Image generation + editing

`resources.py` coordinates a **time-slice swap**: park the 35B (kill
llama-server, free RAM+VRAM) → run `stable-diffusion.cpp` (FLUX.2 klein 4B,
Vulkan) → reload the 35B. `tools/handlers_image.py` exposes `generate_image`,
`edit_image`, `custom_image` (spec parser: style/mood/color/ratio). Images land
in the project `images\` or workspace and are journaled.

## 5. Part 1 — "build ROX N's own capabilities" (the last build phase)

The final phase gave ROX N the ability to *learn* and *build*, so it can take a
single prompt and produce whole projects:

- `tools/handlers_rag.py` — `ingest_docs` / `search_docs` / `list_langpacks` /
  `ingest_langpack` (knowledge category).
- `langpacks.py` — curated TS/React/Tailwind/Vite/Verilog cheatsheets; the
  write path injects the matching pack for the file type being written.
- `tools/handlers_build.py` — `setup_toolchain` (npm/winget/pip per stack) and
  `build_project` is a **native** flow in `rox.py` (plan → write → audit →
  repair → verify).
- `tools/handlers_self.py` — `edit_self`/`backup_self`/`restore_self`/
  `list_backups`/`restart_self`: ROX N may edit its own core files with backup
  + syntax validation + restart flag.
- `rox.py` gained `build_project`, `_gen_file`, `_plan_project`,
  `_verify_and_repair` (verify-driven repair loop), `_finish_project`,
  `--resume`/`--finish` CLI flags.

## 6. Part 2 — autonomous project builds (the stress test)

ROX N was given four project prompts to build on its own:

| Project | Result |
|---------|--------|
| 1. Portfolio (Vite+React+TS+Tailwind) | ✅ `npm run build` passes; renders in Chromium |
| 2. Game arcade (5 games) | ✅ `npm run build` passes; renders in Chromium |
| 3. 4-bit CPU (Verilog) | ✅ **iverilog clean; testbench PASS `(5+3)-2=6`; VCD produced** |
| 4. Ray tracer (TS→PNG) | ✅ **`tsc` clean; `output.png` rendered 800×600 shaded scene** |

> After the model-driven repairs stalled on projects 3 and 4 (the 35B could not
> keep multi-module interfaces consistent), the handover phase **completed them
> hands-on**: the CPU was rewritten as a coherent single-cycle design (PC +
> instruction ROM + decoder + register file + ALU + data memory, ISA in
> `cpu_top.v`), and the ray tracer was rewritten as a coherent TS package. Both
> now build and run with a real verification result. See
> `09-BUILT-PROJECTS.md` for the final per-file state.

The stress test surfaced and fixed a long list of builder bugs — every one of
them is now handled in `rox.py`/`tools/handlers_fs.py`:

- vite/esbuild emit **absolute paths** in errors → `_project_rel()` resolves
  them to real project-relative files (previously repairs wrote to bogus nested
  dirs).
- ANSI color codes corrupted parsed file names → stripped before parsing.
- Markdown code-fences / bare language tags ("verilog") leaked into file
  bodies → stripped in `_clean_fences()` and `_gen_file`; Verilog `timescale`
  backtick auto-restored on write.
- Truncated files (missing `endmodule`, unclosed JSX) → truncation detection +
  "complete the file" retry (`max_tokens` 4096 → 6000).
- Missing npm modules → auto `npm install`; vite entry-module errors →
  regenerate `vite.config.ts`; assembler errors → regenerate `assembler.py`.
- Files that fail repeatedly → clean no-commentary rewrite after 2 attempts.
- Long runs that outlive a shell → detached batch launchers + `--finish` mode
  (no re-plan, install + verify + repair only).

**Honest limitation:** the 35B/8K-context model cannot reliably maintain
strict cross-file type/port contracts across regenerations (Verilog module
ports, TS interfaces). ROX N now handles everything up to that line
autonomously; the two ⚠️ projects are the documented ceiling.

## 7. What is proven vs not

**Proven:** deterministic feature layer 100% on 450,000 generated cases
(arithmetic, safety, retrieval, fact-extraction, tool-routing, memory); memory
persistence across sessions; 145 tool tests + 38 build tests; the two web
projects build and render; image gen/edit works live.

**Not proven:** rented-GPU training (all staged, CPU-verified only); the
500M/1B training targets (costed, not run); long-horizon autonomy.

---

_Next: `02-ARCHITECTURE.md`._