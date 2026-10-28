# 10 — Security Model

ROX N is a local personal assistant with real OS access via tools. The
security model is **defense-in-depth**: the shell gate, the tool
permission tiers, and the safety lockout are independent layers, so no
single model judgment failure can do damage.

## Layer 1 — Shell command gate (`tools/shell_gate.py`)

Every free-text command (`bash`/`run_command`/`shell`) is classified
**before** execution. This does not rely on the model's judgment.

**Verdicts:**
- **allow** (Tier 0/1) — auto-run
- **ask** (Tier 2) — human y/n in chat
- **deny** (Tier 3 / hard block) — never executed

**Bypass defenses (all verified by tests):**
| Attack | Defense |
|---|---|
| `dir && format c:` | chain split on `& ; | \`` |
| `type x | cmd` | piping-to-execution detection |
| `cmd /c format c:` | wrapper unwrap + recursion |
| `powershell -c iex 'x'` | wrapper unwrap + deny patterns |
| `del x.txt` (PS alias) | alias resolution → Remove-Item → ask |
| `python -c "..."` | indirect-exec flag → ask |
| `node -e '...'` | indirect-exec flag → ask |
| `..\..\evil.bat` | path-traversal detection |
| `Set-MpPreference` | hard deny pattern |
| `-EncodedCommand` | hard deny pattern |
| `net user / runas / wmic / diskpart / bcdedit` | T3 deny |

**Principle: do not rely on the model's judgment.** The gate is
deterministic and tested.

## Layer 2 — Tool permission tiers (`tools/permissions.py`)

| Tier | Tools | Policy |
|---|---|---|
| 0 | memory, calc, read-only search/glob/grep, web_fetch, info | auto, no prompt |
| 1 | file writes, git push, run commands, installs, browser | **ask y/n in chat** |
| 2 | cloud CLIs, secrets, billing, IAM, destructive ops | **disabled** unless `allow_tier2` |

Config (`config.json → tools`): `enabled` (category allowlist),
`auto_allow` (Tier-1 that skip confirm), `block`, `allow_tier2`,
`ask_confirms`.

## Layer 3 — Safe executor (`tools/exec.py`)

- Handlers run with a **90s timeout** in a worker thread
- Results capped at **6000 chars** (no context flooding)
- Tier-1 confirm gate via `ctx.ask_callback`
- Unknown tools → error (never silent)

## Layer 4 — Safety lockout (`attachments.lockout_check`)

Crisis-phrase detection (self-harm / suicide patterns) → hard,
supportive redirect before any processing. Validated at F1 1.0 on
50,000 cases (no over-refusal).

## Layer 5 — OS hardening (host-level, documented in the plan)

The intended deployment posture:
- Run as a **standard user** (UAC is the hard wall for Tier 2/3)
- Execution policy `RemoteSigned`
- PowerShell Constrained Language Mode as an option
- Scoped filesystem (project folder) via NTFS ACLs
- Script Block Logging / Transcription for audit
- Never store cloud credentials in the agent profile

Current state: ROX N itself is a normal Python process; the gates above
are its in-app enforcement. Cloud/DevOps tools are registered but
Tier-2-disabled and return honest "requires X" — never fake success.

## What is NOT exposed

- Secrets/credentials: `secrets_set` refuses to write from a tool call
- Destructive system ops: `format`, `diskpart`, `net user`, `shutdown`,
  `iex`, `Set-MpPreference`, `Get-Credential` — all T3 denied
- Cloud admin: aws/gcloud/kubectl/terraform/billing/IAM — Tier-2 disabled
- Offensive pentest tooling: returns "not bundled; run in an authorized
  sandbox"

## Threat model summary

| Threat | Mitigation |
|---|---|
| Model emits dangerous command | shell gate deny/ask before run |
| Model browses tool menus instead of acting | meta-tools removed; intent forces real tools |
| Prompt injection via files | tools are permission-gated; shell gate is deterministic |
| VRAM/RAM exhaustion | duplicate-server guard, RAM guard, CPU-only Ollama |
| Unintended file writes | Tier-1 confirm gate + journaling |
| Data exfiltration | everything local; no cloud paths; network tools are explicit (web_fetch/http_request) and visible |

## Honest residual risks

- Free-text commands that are **unlisted** default to `ask` (safe
  default) — but a long chain of unlisted commands could be tedious to
  review.
- The 35B has knowledge of the tool format; a determined prompt could
  try edge cases, but the gate is deterministic and independent.
- Ollama/network tools are local-only but still explicit network
  actions — user-visible when called.