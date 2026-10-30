# Coal - Complete System

A fully local personal AI: **Qwen3.6-35B-A3B brain + Coal body**
(memory, personality, tools, vision, documents, safety). Nothing leaves
your machine.

## Install

```powershell
cd "C:\Users\WERU1\OneDrive\Documents\Default Project\Coal\lm_track\coal_chat"
python install.py            # links model + server into Program Files, writes config
python install.py --check    # verify
```

Install location: `C:\Users\WERU1\AppData\Local\Programs\Coal\`
```
models\  Coal-35B-A3B-Q4_K_M.gguf + mmproj (vision)
server\  llama-server.exe (llama.cpp)
logs\    llama_server.log, coal.jsonl
config.json
```

## Model source (serving artifact vs. HF source)

Coal serves **`Coal-35B-A3B-Coal`** — a Coal branded build of the open
`Qwen/Qwen3.6-35B-A3B` weights (Apache-2.0, **bit-identical weights**) — from
the GGUF at `D:\Coal_MODELS\Coal-35B-A3B-Coal-Q4_K_M.gguf` via llama.cpp.
See `MODEL_CARD.md` / `NOTICE.md`; identity via `coal.py --manifest`. The
**HuggingFace-format source** of the base (the text backbone of
`Qwen/Qwen3.6-35B-A3B`) is downloaded at `D:\Coal_HF\Qwen3.6-35B-A3B\`
(~67 GB: config.json, tokenizer.json, 26 model.safetensors shards) and recorded
in `config.json` → `model.hf_source` / `model.hf_repos`.

- GGUF = serving (fast, quantized) · HF = source for **weight-level** work
  (abliteration, LoRA fine-tune, merge, re-quantize).
- Verified: the HF text config matches the GGUF header exactly
  (40 layers, hidden 2048, 16 heads, 2 KV, top-8 experts, ctx 262144).
- Weight-level ops on a 35B MoE need ≥ 70 GB RAM/VRAM (bf16) → the rented-GPU
  path (`gpu/RUNBOOK.md`), not this 24 GB box.

## Run

```powershell
python coal.py                       # interactive chat
python coal.py --say "hello"         # one shot
python coal.py --status              # everything, as JSON
python coal.py --session work        # named session
```

The server auto-starts if it is not running.

## What it does

| Capability | How |
|-----------|-----|
| Broad knowledge / reasoning / coding | Qwen3.6-35B-A3B (35B total / 3B active MoE) |
| **Forever memory** across sessions | `memory/` (5 tiers, SQLite + nomic embeddings) |
| **Detective board** — structured, provenance-rich memory of everything Coal learns, including *what it thought* | `board/` (archivist builds it from conversations) |
| Grounded answers from your files | `rag.py` (ingest + retrieve) |
| Reliable math | `attachments.tool_gate` (calculator) |
| Reads images / screenshots / diagrams | `vision.py` (mmproj) |
| Learns *how you talk* | `personality.py` (adapts traits) |
| Session save / resume / export | `session.py` |
| Task-adaptive model + thinking | `router.py` |
| Safe responses | `attachments.lockout_check` + model alignment |
| **~190 tools (13 categories)** | `tools/` (lazy-loaded, permission-gated, sandboxed) |
| Logs, latency, tool traces | `observability.py` |

## How a turn flows

```
you type (or drop an image)
  safety check            -> crisis? hard redirect
  calculator              -> arithmetic? answer directly
  router                  -> kind + model + thinking flag
  memory assemble         -> profile + facts + past turns
  rag retrieve            -> top document chunks
  personality prompt      -> adapted system prompt
  INTENT-FIRST            -> detect purpose -> force the specific tool
  lazy-load schemas       -> only the needed category's tools (capped 30)
  stream to Qwen 35B      -> live tokens (code content passes capture reasoning)
  execute tools           -> native (memory) or executor (fs/git/exec/web/db/browser)
  store + consolidate     -> facts extracted by the model, profile updated
  session saved
```

**Intent-first tool calling** (`tools/intent.py`): Coal reads *what you
want done*, then calls the specific tool. High-confidence intents
("make a file called X on my desktop") force the tool — e.g. `write_file`
writes the real file (the model's reasoning is captured as content).
Verified live: "make a guard.py that blocks SQL injection" → created
`Desktop\guard.py` with working code.

## Tools (347 across 13 categories)

Registered in `tools/specs.py`, executed safely by `tools/exec.py`,
permission-gated by `tools/permissions.py`. Only the router-detected
category's tools are loaded into the prompt per turn (capped at 30),
plus memory tools always. Categories:

| Category | Tools | Tier |
|----------|-------|------|
| filesystem | 33 read/write/edit/zip/patch | read=auto, write=confirm |
| execution | 29 bash/run_script(multi-lang)/tests/install | **shell-gate** |
| search | 25 glob/grep/symbols/diagnostics | auto |
| git | 39 status/commit/push/PR/CI/gh | read=auto, mutate=confirm |
| web | 20 fetch/search/ocr(graphql, npm, pypi, github, SO) | auto |
| browser | 23 navigate/click/type/screenshot (**real playwright**) | auto |
| database | 22 sqlite/vector-db/object-storage | read=auto, write=confirm |
| cloud | 58 aws/kubectl/docker/terraform/secrets | **disabled (honest stubs)** |
| monitoring | 16 logs/metrics/sentry/sast/secret-scan | auto/confirm |
| saas | 7 mcp_* (Stripe/Slack/Jira) | **disabled** |
| orchestration | 33 todo/plan/subagents/checkpoints/memory | auto |
| output | 14 export_pdf/readme/diagram/release | auto/confirm |
| system | 21 ps/df/netstat/clipboard/systemctl | auto/confirm |
| project | 8 create/open/scan/status/journal/audit/map/related | confirm/open |

**Shell security** (`tools/shell_gate.py`): every free-text command runs
through the CMD + PowerShell tier tables:
- **T0 read-only** (dir, git status, Get-ChildItem…) → auto
- **T1 project dev** (mkdir, Set-Content…) → auto inside workspace
- **T2 elevated/destructive** (del, taskkill, reg, net…) → **asks y/n**
- **T3 never** (format, diskpart, net user, iex, -EncodedCommand,
  Set-MpPreference…) → **blocked, never runs**

Defenses: full-command tokenization, chaining split (`& && ; | \``),
wrapper unwrap (`cmd /c`, `powershell -c`), alias resolution (`rm/del/
iwr/iex`), indirect-exec flags (`python -c`, `node -e`), path traversal
(`..\`), piping-to-execution (`curl|cmd`, `iwr|iex`).

**Permission tiers:** Tier 0 auto (memory, calc, read-only search, glob,
grep, web_fetch) · Tier 1 **ask-confirm in chat** (file writes, git push)
· Tier 2 disabled by default (cloud CLIs, secrets, billing, IAM).
Configure in `config.json` → `tools.`:
`enabled`, `auto_allow`, `allow_tier2`, `ask_confirms`.

## Detective board (structured memory + "what Coal thought")

Beyond flat forever-memory, Coal keeps a **detective board**: a structured,
cross-referenced knowledge base derived from every conversation, where each
card records Coal's own reasoning as provenance.

- **Archivist** (`board/archivist.py`): a small local model (`coaln-3b` via
  Ollama) reads each exchange — including Coal's thinking — and writes
  entities, typed relations, per-conversation dossiers, a timeline, and
  provenance.
- **Runs in the idle window** (`python coal.py --archive`, or session end):
  it parks the 35B, runs the archivist, reloads the 35B (same time-slice
  pattern as image generation). Optional background idle archiver via
  `board.auto_archive`.
- **Storage vs RAM**: the board lives on disk (`~/.coal/board.db`, unbounded);
  a bounded **hot-graph cache** (`board/cache.py`) keeps the working set in RAM.
- **Retrieval** (`board/retrieve.py`): FTS5 + vectors + entity match →
  graph expansion → a compact board card injected into the prompt.
- **Tools**: `board_search`, `board_entity`, `board_related`, `board_timeline`,
  `board_dossier`, `board_show` (openable card incl. reasoning), `board_archive`,
  `board_stats`.
- **Openable cards** (`board/export.py`): `python coal.py --board-export cards.json`
  writes every card with Coal's full reasoning attached.
- **UI** (`board/ui.py` + `board/ui.html`): a flat, solid-color local web page —
  `python board/ui.py` (or `board_ui.bat`, or `python coal.py --board-ui`) serves
  `http://127.0.0.1:8790/` with entities, relations, conversations, the timeline,
  and each card's reasoning.

Files: `board/store.py`, `queue.py`, `archivist.py`, `resolve.py`, `builder.py`,
`retrieve.py`, `cache.py`, `export.py`, `ui.py`, `ui.html`; `tools/handlers_board.py`.

## Project awareness (multi-file coding without hallucination)Coal remembers everything about a project — every file, every change,
every relationship — so coding large multi-file systems doesn't guess.

- **`project/`** package: `project.py` (file ledger + architecture map),
  `journal.py` (fine-grained change log), `audit.py` (consistency check),
  `context.py` (anti-hallucination prompt context).
- **Projects live on your Desktop** at `Desktop\Coal Projects\<name>\`;
  the memory ledger stays clean in `~/.coal/projects/<name>\`.
- **Every write/edit/delete is journaled automatically** (hooks in the
  file tools) — ask "what changed in main.py?" and it answers from the
  real log.
- **Audit** finds broken imports, duplicate symbols, orphans, TODOs.
- **Related** maps which files import which.
- **Ask-name flow**: "create a project" → Coal asks if you have a name
  or should it decide → creates the folder.
- Tools: `project_new`, `project_open`, `project_scan`, `project_status`,
  `project_journal`, `project_audit`, `project_map`, `project_related`.

## Image generation (FLUX.2 klein 4B + resource swap)

Coal generates images with **FLUX.2 klein 4B** (Q8_0, ~4GB) via
`stable-diffusion.cpp` (Vulkan) — the best/fastest model for your RX 570.
Because two heavy models can't share 24GB RAM, it **time-slices**:

1. You ask: "make me an image of a robot arm" → detected as `generate_image`
2. Coal **parks the 35B** (kills llama-server, frees ~10-15GB RAM + 8GB VRAM)
3. `sd-cli` runs on the freed Vulkan GPU (~30-60s for 512×512, 4 steps)
4. PNG saved into the project `images\` (or workspace) + **journaled**
5. **35B reloads** and is ready again (memory/personality safe on disk)

Images are generated at **1024×1024** (FLUX.2 klein's native resolution,
~2-4 MB, ~2.5-4 min on the RX 570) with a quality negative-prompt and a
random seed each time. They land in `~/.coal/work/images\` or
`<project>\images\`. Try: `make me an image of a dragon`, `draw a
landscape`, `a majestic eagle over mountains`, `generate a character
for my game`, `make a logo for my startup`.

**Image editing** also works (same swap): `edit this image into a
watercolor`, `turn my logo.png into a cartoon`, `change test_fox.png to
a painting`, `recolor this picture to blue` — uses FLUX.2 klein's
reference/init edit modes, saves `edited_...` into the project + journals.

**Custom images from your specifications** (`custom_image`): Coal parses
subject + style + mood + color + aspect ratio from a natural request and
generates (or recreates an existing image) to match. Examples:
- `make me a dragon in cyberpunk style, red, 16:9` → 1280×720 cyberpunk dragon
- `generate a custom portrait, watercolor, pastel, square`
- `custom image of a robot, dark, moody`
- `recreate my logo.png as a cartoon`

Styles: cyberpunk, watercolor, oil painting, pixel art, anime, cartoon,
photorealistic, 3d render, minimalist, vintage, neon, comic, sketch,
fantasy, steampunk, gothic, isometric, pastel... Ratios: square/1:1,
16:9, 9:16, 4:3, 3:4, landscape, portrait. Colors + moods supported too.

**Image understanding** works too (no swap needed): `what is in this
image`, `describe this photo`, `read the text in this image` → uses the
35B's vision (mmproj) / `ocr_image`.

## Chip design (RTL) + blue-team security

**Chip design:** `chip_architect.py` drives `chip-design-ai-v4` (a local Qwen2
3.1B, 32K ctx) to plan module port lists and review RTL against contracts.
`project/contract.py` stores a per-project **interface contract** (spec-first):
for HDL builds, every module's ports **and name** are planned before
generation, injected into the write prompt, and checked deterministically in
`_verify_and_repair` (`[contract]` conformance). Verified: the generated
ALU/regfile matched their contract ports exactly, and the testbench
instantiated the top module with only its declared ports.

**Mechanical HDL guardrails** (deterministic, no model) run every verify
round: `hdl_fix` (strip comment bloat + hoist declarations out of procedural
blocks), `_fix_module_refs` (reconcile instantiation names to defined modules,
e.g. `data_memory`→`data_mem`), `_fix_port_connections` (drop `.port(...)`
connections a module doesn't declare), `_fix_top_instantiation` (no submodule
may instantiate the top). The iverilog verify uses `-g2012` (SystemVerilog).

Tools: `chip_plan`, `chip_review`, `chip_verify`.

**Blue team (security category, local, real):**
- `scan_secrets` — AWS keys, private keys, JWTs, tokens, high-entropy creds.
- `sast_check` — eval/exec/shell=True, raw SQL, hardcoded creds, weak crypto,
  unsafe pickle/yaml, SSRF.
- `parse_logs` — JSONL/CLF structured log triage with IOC surfacing.
- `osint_lookup` — DNS/PTR, geo+ASN, HTTP headers, certificate transparency.

Tests: `test_security.py` (16), `test_chip.py` (9 + `--live` 11).

## Files

| File | Role |
|------|------|
| `coal.py` | unified assistant + CLI |
| `coal_config.py` + `config.json` | single source of config |
| `server_manager.py` | start/stop/health, RAM guard, Vulkan auto-tune |
| `coal_template.py` | exact chat template + tool XML |
| `streaming.py` | live token output |
| `personality.py` | adaptive personality |
| `session.py` | save/resume/export |
| `vision.py` | image input |
| `resources.py` | image-gen resource swap (park 35B / generate / reload) |
| `tools/handlers_image.py` | `generate_image` handler (FLUX.2 klein 4B) |
| `rag.py` | document ingestion + retrieval |
| `router.py` | task routing + thinking control |
| `observability.py` | logs + metrics |
| `project/` | project awareness (ledger, journal, audit, context) |
| `memory/` | forever memory (store, embed, index, retrieve, consolidate, profile, tools, assemble) |
| `tools/` | **~347 tools, 13 categories** — registry, permissions, shell gate, intent, safe executor, handlers |
| `tools/shell_gate.py` | CMD + PowerShell tier tables + bypass defenses |
| `tools/shell.py` | gate-then-run for free-text commands |
| `tools/intent.py` | purpose → specific tool call (intent-first) |
| `tools/handlers_*.py` | fs, exec, other, misc, browser, db, web2, cloud |
| `test_tools.py` | 93 tool-layer tests (tiers, intent, executor) |
| `eval/` | 450K-case test suite + report |
| `install.py` | setup |

## Memory (forever)

Stored under `~/.coal/`:
```
memory.db        SQLite: sessions, messages, facts, entities, summaries
vectors/         nomic-embed-text embeddings (768-d, local)
profile.json     user profile
personality.json adapted traits
rag/             document index
sessions/        conversation files
```
Tell it something once; it remembers across sessions. Delete `~/.coal`
to wipe everything.

## Verify / evaluate

```powershell
python eval/suite.py --scale huge --llm none     # 450K deterministic
python eval_live.py --n 10                        # live model QA + recall
python eval/final_report.py                       # regenerate report
python test_tools.py                              # tool layer tests
```

## GPU (Vulkan)

The server runs the local **Vulkan** llama.cpp build (2.46.0) with
`-ngl 8` (8 of 40 layers on the Radeon RX 570's 8 GB VRAM). `server_manager`
auto-tunes: if the GPU allocation fails (VRAM full), it steps `gpu_layers`
down and retries, ending at CPU-only if needed. A `fallback\` Vulkan build
(2.31.2) sits alongside the main server for recovery.

**Why it matters:** tokens/sec is roughly the same as CPU (the RX 570 is
an older card — the layer offload is compute-neutral here), but the model's
**RAM footprint drops from ~13 GB to ~7 GB**, taking free RAM from ~0.5 GB
to ~9-10 GB. That headroom is what keeps Ollama (embeddings) and the tools
alive at the same time as the brain.

## Performance (your machine)

- 35B Q4_K_M on 8 GPU layers + CPU mmap: ~5.5-7 tok/s, ~40-60s per reply
- Free RAM with Vulkan: ~9-10 GB (was 0.5 GB CPU-only) — Ollama stays up
- Faster chat option: a smaller local model via Ollama (set as fallback, or
  `COAL_MODEL` override)

## RAM and embeddings

With Vulkan the 35B leaves enough RAM for Ollama's `nomic-embed-text`, so
the embedder uses semantic 768-d embeddings by default. If Ollama is
evicted (heavy load), it falls back to in-process TF-IDF automatically.
The memory system is proven at 100% on 50,000 recall tests with the
TF-IDF path, so recall always works; nomic just improves paraphrase
matching.

