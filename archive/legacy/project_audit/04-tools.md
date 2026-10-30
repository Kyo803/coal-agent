# 04 — The Tool Layer (`tools/`)

## Overview

Coal ships **357 tools across 14 categories**, all lazy-loaded,
permission-gated, and executed safely. The layer is:

```
specs.py         -> tool registry (356 tools, 14 categories)
permissions.py   -> Tier 0/1/2 access model
exec.py          -> safe executor (timeout, result cap, confirm gate)
shell.py         -> gate-then-run for free-text commands
shell_gate.py    -> CMD + PowerShell command classifier
intent.py        -> purpose → specific tool (intent-first)
handlers_*.py    -> actual tool implementations (8 modules)
```

## Category inventory

| Category | Tools | Example |
|---|---|---|
| cloud | 58 | aws_cli, kubectl, docker_build, terraform (Tier-2 disabled) |
| git | 39 | status, commit, push, PRs, workflows (gh-backed) |
| execution | 36 | bash, run_script (python/node/pwsh/cmd/bash), tests |
| filesystem | 33 | read/write/edit/delete/zip/patch |
| orchestration | 33 | todo, plan_mode, subagents, checkpoints, memory |
| search | 26 | glob, grep, symbols, diagnostics |
| browser | 23 | navigate/click/type/screenshot (playwright) |
| database | 22 | sqlite, vector-db, object-storage |
| system | 21 | ps, df, netstat, clipboard |
| web | 20 | fetch, search, ocr_image, graphql, pypi/npm/github |
| monitoring | 16 | logs, metrics, sentry, sast, secret-scan |
| output | 13 | export_pdf, readme, diagram, release |
| saas | 7 | generate_image (real), call_llm, mcp_* |
| project | 8 | create/open/scan/status/journal/audit/map/related |

(Counts vary slightly by registry state; `len(tools.SPECS)` is canonical.)

## `permissions.py` — three tiers

| Tier | Behavior | Examples |
|---|---|---|
| **0 auto** | never prompts | memory, calc, read-only search, glob/grep, web_fetch |
| **1 confirm** | asks y/n in chat | file writes, git push, run commands, installs |
| **2 disabled** | off by default | cloud CLIs, secrets, billing, IAM |

Config-driven overrides (`config.json → tools`):
- `enabled` — which categories are exposed
- `auto_allow` — Tier-1 tools that skip confirmation
- `block` — always refused
- `allow_tier2` — Tier-2 tools to enable
- `ask_confirms` — master toggle

## `exec.py` — safe executor

`ToolExecutor.run(name, args, ctx)`:
1. Looks up the spec; unknown → error
2. Blocks Tier-2 unless allowed
3. Prompts (Tier-1) via `ctx.ask_callback` — user types y/n
4. Runs the handler in a thread with a **90s timeout**
5. Caps result at **6000 chars**
6. Returns `{ok, output, tool, ms}` and traces to `ctx.trace`

`ExecContext` holds the workspace, ask/notify callbacks, todos,
scheduled tasks, mcp tools, trace.

**`lazy_schemas(text, perms, ensure=None)`** — the lazy-loading core:
- Classifies the message → which categories to expose
- Prioritizes categories, caps at **30 tools** per turn
- Always includes memory tools
- `ensure=` guarantees the intent-forced tool is present
- Intentionally does **NOT** expose `list_tools`/`use_category` (meta
  tools) — they tempted the model to "browse menus" instead of acting.

## `shell_gate.py` — the command security wall

Every free-text command (`bash`/`run_command`/`shell`) goes through a
strict classifier before execution. Verdicts: **allow | ask | deny**.

**Tier tables (as DATA):**
- T0 read-only: `dir`, `type`, `git`, `python`, `pip`, `Get-*`, ...
- T1 project dev: `mkdir`, `copy`, `New-Item`, `Set-Content`, ...
- T2 elevated → ask: `del`, `rmdir /s`, `taskkill`, `reg`, `setx`,
  `Remove-Item -Recurse`, `Stop-Process`, `Invoke-WebRequest`, ...
- T3 never → deny: `format`, `diskpart`, `net user`, `runas`, `wmic`,
  `shutdown`, `bcdedit`, `Invoke-Expression`, `-EncodedCommand`,
  `Set-MpPreference`, `Get-Credential`, ...

**Bypass defenses (all tested):**
- full-command tokenization (not just first word)
- chaining split on `& && ; | \`` (a "safe" prefix can't smuggle)
- wrapper unwrap: `cmd /c "..."`, `powershell -c "..."`, `pwsh -Command`
- alias resolution: `rm/del/ri → Remove-Item`, `iwr/curl/wget →
  Invoke-WebRequest`, `iex → Invoke-Expression`
- indirect-exec flags: `python -c`, `node -e`, `npx`, `-enc`
- path traversal / project-escape: `..\..\`
- piping-to-execution: `curl ... | cmd`, `iwr ... | iex`

## `shell.py` — gate-then-run

`run_safe(command, workspace, ask_callback)`:
- `allow` → execute (T0/T1)
- `ask` → prompt user (T2); y → run, n → declined
- `deny` → refuse with reason, **never executed**

## `intent.py` — the purpose interpreter

`detect_intent(text)` → `Intent(tool, confidence, args, reason)`.

Rule table (ordered; first match wins):
- **Image gen** (highest): "make/draw/render an image/picture/photo/logo/
  icon/art", "generate a character/landscape", bare subjects
  ("a majestic eagle over mountains")
- **Image understanding**: "what's in this image", "describe this photo",
  "read the text in this image" → ocr_image
- **File creation**: "make me a <lang> script/app/game", "create a file
  called X"
- **Edit / read / inspect**: edit_file, read_file, glob
- **Run**: run_command / run_script / install_package
- **Git**: git_status/commit/push/pull/log
- **Memory**: remember / search_memory
- **Project**: project_new/open/audit/journal/status
- **Web**: web_fetch / browser_navigate / sql_query

`needs_force(intent)` → true for high confidence → `coal.py` forces the
tool and guarantees its schema.

## Handler modules

| Module | Tools | Notes |
|---|---|---|
| `handlers_fs.py` | filesystem + search | read/write/edit/delete/zip/glob/grep; **auto-journals mutations** via `set_journal_hook()` |
| `handlers_exec.py` | execution | `run_script` dispatches python/node/powershell/cmd/bash; free-text commands go through `run_safe` (shell gate) |
| `handlers_other.py` | git + web + database | git, web_fetch, web_search, read_pdf/docx, sql |
| `handlers_misc.py` | orchestration + output + system | todo, ask_user, notify, mcp stubs, export, ps/df |
| `handlers_browser.py` | browser (playwright) | persistent headless Chromium, navigate/click/type/screenshot |
| `handlers_db.py` | database advanced | sqlite DDL/DML, migrations, backup/restore, vector-db (→ memory index), object storage |
| `handlers_web2.py` | web advanced | graphql, ocr_image (→ vision model), pypi/npm/github/SO search |
| `handlers_cloud.py` | cloud/monitoring/git-advanced | honest Tier-2 stubs (never fake success); gh-backed PRs/CI |
| `handlers_project.py` | project awareness | create/open/scan/status/journal/audit/map/related |
| `handlers_image.py` | image generation | FLUX.2 klein via `resources.swap_for_image` |

## Key incident learnings baked into the layer

1. Meta-tools (`list_tools`/`use_category`) were removed from prompts —
   the model used them to "browse" instead of doing work.
2. Forced tools are guaranteed present (`ensure=`) — an intent without
   its tool exposed silently failed.
3. `bash`/`run_command` are **auto-tier** in exec.py because the shell
   gate already provides per-command ask/deny — no double-prompting.
4. Tool results are capped so context isn't flooded.
5. `write_file` content generation uses a **clean prompt + 4096 tokens**
   so session history can't make the model narrate instead of writing.