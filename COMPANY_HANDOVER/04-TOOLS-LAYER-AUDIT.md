# 04 — TOOLS LAYER AUDIT (`tools/` — every file)

The tool layer is where ROX N "does things". **369 tools registered across 17
category groups.** All files in `tools/` are documented here.

---

## Registry / execution / policy

### `tools/specs.py` (63.5 KB) — THE TOOL REGISTRY
Single source of truth for every tool: name, category, json-schema params,
required args, permission tier, and handler. Exposes `SPECS`, `get(name)`,
`all_specs()`, `lazy_schemas(ensure=…)`, `CATEGORIES` (17 groups), and
`MEMORY_TOOLS` / `NATIVE_TOOLS` (tools handled natively by `rox.py`, not the
executor — `build_project` lives here). **~369 tools.** Adding a tool = add a
`_mk(...)` row here + the handler function.

### `tools/permissions.py` (3.8 KB) — permission model
`Permissions` with tiers: **Tier 0** auto (memory, calc, read-only search,
glob, grep, web_fetch) · **Tier 1** ask-confirm (file writes, git push) ·
**Tier 2** disabled by default (cloud CLIs, secrets, billing, IAM). Configured
via `config.json → tools.` (`enabled`, `auto_allow`, `allow_tier2`,
`ask_confirms`). `needs_confirm(name)` is used by the executor and tests.

### `tools/exec.py` (11.3 KB) — SAFE EXECUTOR
`ToolExecutor(ctx, perms)`: permission gate → 90 s timeout → result cap (6 KB)
→ journal/project hooks. `ExecContext` carries `workspace`, `ask_callback`,
`notify_callback`, `project`. `run(name, args, category)` looks up the spec,
submits the handler to a thread pool. This is the only path handlers execute
through.

## Shell security

### `tools/shell_gate.py` (14.4 KB) — CMD + PowerShell tier tables + bypass defenses
The security core. Encodes:
- **T0 read-only** (dir, git status, Get-ChildItem…) → auto
- **T1 project dev** (mkdir, Set-Content…) → auto inside workspace
- **T2 elevated/destructive** (del, taskkill, reg, net…) → asks y/n
- **T3 never** (format, diskpart, net user, iex, -EncodedCommand,
  Set-MpPreference…) → blocked, never runs

Defenses: full-command tokenization, chaining split (`& && ; |` backtick),
wrapper unwrap (`cmd /c`, `powershell -c`), alias resolution (`rm/del/iwr/
iex`), indirect-exec flags (`python -c`, `node -e`), path traversal (`..\`),
piping-to-execution (`curl|cmd`, `iwr|iex`). All verified by tests.

### `tools/shell.py` (3.7 KB) — safe shell runner
`run_safe(command, workspace, ask_callback, timeout, cwd)` — the *only* path
free-text commands execute through: gate → run → verdict (deny/ask/ok).

## Intent (purpose-first)

### `tools/intent.py` (17.1 KB) — intent interpreter
`detect_intent(text)` → tool + args + confidence. Rules for: write_file
(filename extraction with `_extract_filename`), build_project (whole-project
phrases), project_new, generate_image/edit_image/custom_image, web_search,
memory tools, and more. `needs_force()` decides whether to bypass the model's
tool-call and run the intent directly. High-confidence = forced.

## Handlers (the actual implementations)

### `tools/handlers_fs.py` (13.5 KB) — filesystem + search (cat. 1 & 2)
`write_file` (with `_clean_fences` — strips leaked markdown fences and restores
Verilog `timescale` backtick), `edit_file`, `append_file`, `delete_file`,
`move_file`, `read_file`, `list_dir`, `glob`, `grep`, zip/patch helpers.
Auto-journals when inside the open project. **Careful:** `_clean_fences` and
the backtick restoration are deliberate model-output corrections — keep them.

### `tools/handlers_exec.py` (7.2 KB) — execution + runtime (cat. 3)
`run_command` (shell-gated, supports `cwd`), `bash`, `shell`,
`run_script` (python/node/powershell/cmd/bash dispatcher), `install_package`.
All free-text commands go through `run_safe` (shell gate).

### `tools/handlers_other.py` (9.1 KB) — git, web, database (cat. 4, 5, 7)
Git/gh tools (status/commit/push/PR, honest when gh isn't logged in), web
fetch + `web_search` (**Bing fallback via pure urllib**, no ddgs needed),
`ocr_image` (routes to the vision model), package/registry search.

### `tools/handlers_misc.py` (6.2 KB) — orchestration, output, system (cat. 11-13)
Todo/plan/subagent helpers, output/delivery (present_files, readme, diagram,
release), system admin (ps/df/netstat/clipboard).

### `tools/handlers_browser.py` (9.1 KB) — browser + UI (cat. 6)
Real Playwright on persistent headless Chromium: navigate, snapshot, click,
type, screenshot.

### `tools/handlers_db.py` (7.2 KB) — database advanced (cat. 7)
SQLite DDL/DML, migrations, backup/restore, seed, vector-db, object storage.

### `tools/handlers_web2.py` (6.1 KB) — web advanced (cat. 5)
GraphQL, OCR via the vision model, npm/pypi/github/stackoverflow search.

### `tools/handlers_cloud.py` (20.6 KB) — cloud/devops/saas (cat. 4/8-12)
AWS/kubectl/docker/terraform + Stripe/Slack/Jira. **All honest Tier-2 stubs**:
run the CLI if present, else say exactly what's missing. Never fake success.

### `tools/handlers_image.py` (10.1 KB) — image generation + editing
`generate_image`, `edit_image` (ref `-r` / init `-i` modes), `custom_image`
(spec parser: style/mood/color/ratio). Uses `resources.py` to park the 35B,
run `sd-cli`, reload. Saves PNG into project `images\` + journals.

### `tools/handlers_project.py` (4.5 KB) — project awareness tools
`project_new/open/scan/status/journal/audit/map/related` → delegate to the
`project/` package.

### `tools/handlers_rag.py` (5.9 KB) — document ingestion + langpacks (knowledge)
`ingest_docs` (URL/file/folder/text → RAG), `search_docs`, `list_langpacks`,
`ingest_langpack`. ROX N "learns".

### `tools/handlers_build.py` (3.6 KB) — build helpers (cat. build)
`setup_toolchain(stack, dir, prod)` — npm/winget/pip per stack
(web/react/node/python/hdl). `build_project` is registered here with a `None`
handler (it is native in `rox.py`).

### `tools/handlers_self.py` (5.1 KB) — self-modification (cat. self)
`edit_self` (backup → syntax-validate via `py_compile` → write → restart
flag), `backup_self`, `restore_self`, `list_backups`, `restart_self`
(detached relaunch). ROX N may modify its own core files safely.

### `tools/handlers_board.py` — detective board (cat. board)
`board_search`, `board_entity`, `board_related`, `board_timeline`,
`board_dossier`, `board_show` (openable card incl. ROX N's reasoning),
`board_archive`, `board_stats`. Reads the board off `ctx.board` (set by
`rox.py`); see `05-MEMORY-PROJECT-AUDIT.md` for the `board/` package.

### `tools/handlers_security.py` — blue-team scanners (cat. security)
`scan_secrets` (AWS/private keys/JWT/tokens/high-entropy), `sast_check`
(eval/exec/shell=True/raw SQL/hardcoded creds/weak crypto/unsafe
pickle+yaml/SSRF), `parse_logs` (JSONL/CLF triage + IOC surfacing),
`osint_lookup` (DNS/geo+ASN/headers/cert transparency). Local, no CLIs.

### `tools/handlers_chip.py` — chip design (cat. chip)
`chip_plan` (plan module ports via chip-design-ai-v4), `chip_review`
(model checks RTL vs a contract), `chip_verify` (deterministic port
match). Backed by `chip_architect.py` and `project/contract.py`.

### `tools/__init__.py` (0.4 KB) — package marker
Makes `tools` importable; declares the layer ("~300 tools, 13 categories,
lazy-loaded…").

---

## Category groups (`CATEGORIES` in `specs.py`, 17 keys)

`filesystem`, `search`, `execution`, `git`, `web`, `browser`, `database`,
`cloud`, `monitoring`, `saas`, `orchestration`, `output`, `system`, `project`,
`knowledge`, `build`, `self`, `board`, `security`, `chip`.

---

_Next: `05-MEMORY-PROJECT-AUDIT.md`._