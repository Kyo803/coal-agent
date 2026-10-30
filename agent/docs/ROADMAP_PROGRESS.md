# Coal — Roadmap Progress (Phases 0–7)

All phases of the master roadmap are implemented, tested, and green.

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Speed & context (16K, KV q8_0, flash-attn, cache-reuse) | done |
| 1 | `sandbox/` — isolated WSL2 Ubuntu Coal controls | done |
| 2 | `learning/` + `learning/curiosity/` — independent learning | done |
| 3 | `selfimprove/` — autonomous, tested, rollback-safe self-edit | done |
| 4 | `builder/` — extreme-coding state machine + quantum-inspired optimizer | done |
| 5 | `knowledge/` — recall routes, indexing schemes, skills, speed | done |
| 6 | `governance/` — resources, cadence, telemetry, always-on daemon | done |
| 7 | `finetune/` — QLoRA dataset/script/runbook hook | done |

## Autonomy pass — gaps closed (autonomy ON)

- **`autonomy/`** brain added: Study / Observe / Practice / Reflect /
  Improve / Archive, over the curiosity drive + mood.
- **Daemon switched to the brain's activities**, idle-gated + interval-gated
  (900 s), night adds study/reflect/practice; logged.
- **Always-on installed**: Startup `Coal_Daemon.bat` runs `pythonw coal.py
  --daemon` at logon; PID singleton lock. (Running now: pid logged.)
- **Persona**: system prompt now states real capabilities (act, don't hedge).
- **Knowledge routes wired into live answers** (`memory/assemble.py`).
- **Learning writes to the board** (`learning/board_bridge.py`).
- **Self-improve ON** (`dry_run=false`): auto low-risk, experiment the rest,
  core opt-in, anti-oscillation + backups + rollback.

## Regression (all green)

test_tools 145 · test_build 38 · test_board 31 · test_security 16 ·
test_chip 9 · test_learning 25 · test_selfimprove 26 · test_builder 20 ·
test_knowledge 17 · test_governance 15 · test_finetune 14 · test_autonomy 11
→ **367 checks, 0 failures**. Registry: **412 tools / 22 categories**.

See `AUTONOMY.md` for the brain, cadence, and what's still intentionally
manual (practice off by default; core self-edit opt-in; QLoRA hook).

## How to operate it

```
# sandbox (run anything in isolated Ubuntu)
coal.py --say "... in the linux sandbox ..."

# independent learning
coal.py --learn-stats
coal.py --learn "hash tables" [--no-network]

# self-improvement (dry-run by default; ON in this config)
coal.py --improve-status
coal.py --improve

# builder (repair/verify a sandbox project)
coal.py --build NAME DIR --stack python --criteria "file:.../main.py,contains:def main"

# governance daemon
coal.py --daemon-status
coal.py --daemon-once
coal.py --daemon            # foreground always-on

# fine-tune
coal.py --finetune-plan
coal.py --finetune-export
```

## Key safety invariants

- The **sandbox is the boundary**: automount + interop off; the Windows
  host is unreachable from inside; `wsl` is allowed in the shell gate.
- **Self-improvement** defaults to dry-run in code (enabled in this config):
  low-risk auto-applies, tool/code must win an isolated experiment, core
  files need `allow_high_risk`; every apply is backed up + rollback-able;
  anti-oscillation rate limit.
- **Learning** honours robots.txt, rate limits, and a blocked-content
  guardrail; it degrades offline (tfidf embedder, heuristic fallbacks).
- A regression is never applied (scoreboard compare).

## Docs

`SPEED_AND_CONTEXT.md`, `SANDBOX.md`, `LEARNING.md`, `SELFIMPROVE.md`,
`BUILDER.md`, and this file.
