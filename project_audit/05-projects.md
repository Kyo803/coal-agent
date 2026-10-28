# 05 — Project Awareness (`project/`)

## Purpose

ROX N manages **multi-file, multi-folder projects without hallucinating**
about the codebase. It tracks every file (hash-verified), journals every
change, audits consistency, and grounds answers in the real structure.

## Two locations (by design)

| Location | Purpose |
|---|---|
| `Desktop\ROX Projects\<name>\` | The **source** project folder (user-facing) |
| `~/.rox/projects/<name>\` | The **ledger** (memory: DB, journal, architecture) |

Keeping the ledger out of the repo means ROX N's memory never pollutes
the user's project.

## Module map

| Module | Role |
|---|---|
| `project.py` | `Project` model: scan (hash ledger), status, architecture (tree/symbols/imports), related |
| `journal.py` | Fine-grained change journal (append-only JSONL) |
| `audit.py` | Consistency checker: broken imports, dup symbols, TODOs, orphans |
| `context.py` | Budget-aware prompt context (`file_context`, `project_context`) |

## `project.py` — the project model

- `Project.create(name)` / `Project.open(name)` — creates source + ledger
- `desktop_root()` — real Desktop via `SHGetFolderPathW` (OneDrive-safe)
- `slugify()` / `safe_name()` — folder-name validation
- `scan()` — walks the tree, SHA-256-hashes every file, marks
  `new / changed / unchanged / deleted` in the SQLite ledger
- `status()` — file count + recent changes
- `architecture(refresh)` — caches tree + per-module symbols/imports;
  **auto-refreshes** if the on-disk tree no longer matches the cache
- `related(rel)` — which files import it / it imports

## `journal.py` — fine-grained audit log

Append-only JSONL: `{time, iso, file, action, detail, meta}`.
**Every** write/edit/delete/rename is recorded (hooks in `handlers_fs`).
Query methods:
- `history(rel)` — all entries for one file
- `latest(rel)` — most recent
- `today()` — today's changes
- `by_file()` — grouped
- `summary()` — human-readable digest

This is what answers "what changed in main.py?" with **real** history,
not guesses.

## `audit.py` — consistency checker

`Auditor(project).audit()` finds:
- **missing_import** — imports a module with no matching file (stdlib +
  common third-party allowlisted to reduce noise)
- **duplicate_class** — same class name in 2+ files
- **marker** — TODO / FIXME / HACK / XXX
- **orphan** — .py file not imported by anything (excluding main/__init__)

## `context.py` — anti-hallucination context

- `file_context(project, rel)` — full content + symbols + imports +
  recent journal + related files (budget-aware)
- `project_context(project, query)` — file tree + module/symbol map

These are injected into the system prompt when a project is open, so the
model answers from the actual code, not assumptions.

## Tool wiring

8 project tools (`handlers_project.py`): `project_new`, `project_open`,
`project_scan`, `project_status`, `project_journal`, `project_audit`,
`project_map`, `project_related`.

## The create flow (ask-name)

"create a project for X" → ROX N asks the user:
> "Do you have a name, or should I decide?"

- User names it → use that (validated)
- "you decide" → derive a slug from the request ("my robot arm control
  system" → `robot-arm-control-system`)

## Auto-journaling

`handlers_fs.set_journal_hook(fn)` — registered by `Rox` on init. After
every `write_file`/`edit_file`/`append_file`/`delete_file`/`move_file`
that touches a file inside the open project, it records the change.

## Verified behavior

- Created project at `Desktop\ROX Projects\<name>`
- Wrote `src/main.py` → auto-journaled ("created")
- `project_audit` found the intentional missing import + orphan
- `project_related` mapped `scraper.py → parser.py`
- `read my snake.html` → read the real file and explained it