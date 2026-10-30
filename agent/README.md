# agent — the Coal runtime

Coal is an agent that designs hardware and proves it works, then uses the
same hands for software, security and file work. This directory is the
Python runtime behind both the desktop app and the terminal UI.

## Entry points

| Command | What it does |
|---|---|
| `py -3.15 coal.py` | interactive chat (Ollama by default) |
| `py -3.15 coal.py --json-repl` | the protocol the desktop app and TUI drive |
| `py -3.15 coal.py --say "build a 4-bit counter"` | one-shot turn |
| `demo.cmd` | one command: reads the Nebius key, sets `COAL_NO_35B`, starts the TUI |

`COAL_NO_35B=1` is mandatory on a 24 GB machine: it stops the 19.7 GB local
model from ever being loaded. The launcher, TUI and `demo.cmd` all set it.

## Layout

```
coal.py                 entry point: REPL, JSON protocol, one-shot
coal_config.py          config loader (~/.coal/config.json + defaults)
router.py               picks the model/kind for a request
streaming.py            SSE chat client (Nebius / Ollama), tool-call parsing
session.py              conversation transcript
personality.py          tone and preference model
observability.py        turn log and timings
server_manager.py       starts/stops the local llama-server safely
resources.py            RAM-aware model choice
safety.py               deterministic malware-request gate
security_binary.py      PE/ELF triage (headers, entropy, strings, disasm)

chipflow/               the chip engine (see chipflow/README.md)
tools/                  every tool the model can call (see tools/README.md)
board/                  memory board: archivist, cards, provenance
memory/                 embeddings, recall, consolidation
builder/                multi-file project build/verify loop
learning/               self-directed study, curriculum, guardrails
governance/             resource limits and health
project/                project context and journals
sandbox/                isolated Linux sandbox control
selfimprove/            hypothesis → patch → validate loop
autonomy/               background activity loop
missions/               chip mission definitions
eval/                   evaluation runners
tui/                    Go terminal UI (bubbletea)
compute/                ONNX / image worker for heavy generation
docs/                   design notes and reports (see docs/README.md)
data/                   small JSON fixtures used by tests and demos
scripts/                setup and helper scripts

test_*.py               the test suite; run them from this directory
```

## Tests

Run from this directory so the flat imports resolve:

```powershell
py -3.15 test_tools.py          # 434 tool specs, permissions, handlers
py -3.15 test_chipflow.py       # blocks, gate, P&R, waves, floorplan
py -3.15 test_stdin.py          # the desktop/TUI JSON protocol
py -3.15 test_security_tools.py # SAST, secrets, binary triage
py -3.15 test_safety.py         # malware-request refusal gate
py -3.15 test_routing_tools.py  # domain routing (chip / security / web)
```

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `NEBIUS_API_KEY` | — | hosted inference (falls back to Ollama) |
| `COAL_BASE_URL` | Nebius Studio | any OpenAI-compatible endpoint |
| `COAL_AGENT_MODEL` | `nvidia/nemotron-3-super-120b-a12b` | hosted model |
| `COAL_NO_35B` | — | set to `1` to forbid the 19.7 GB local model |
| `COAL_NO_PNR` | — | set to `1` to skip place & route |
| `COAL_CONFIG` | `~/.coal/config.json` | config override |
| `COAL_DIR` | this directory | used by the launchers |

Data (memory, work products, key) lives in `~/.coal/`.
