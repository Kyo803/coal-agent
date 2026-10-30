# Coal — Safe Unattended Autonomy

_Run unattended on a 24 GB / RX 570 8 GB machine **with the user's own work
running alongside**. Two prior crashes came from resource exhaustion; this
setup exists to make sure that cannot happen again._

## Why the 35B must never run here

`Coal-35B-A3B-Coal-Q4_K_M.gguf` is **19.7 GB**. On a 24 GB machine that
leaves ~4 GB for Windows + everything else — loading it is what exhausted
RAM and crashed the PC. So:

- `server_manager.ensure()` / `start()` now **refuse to start** when
  `CoalO_35B=1` is set.
- The supervisor sets that variable **and** actively kills any
  `llama-server.exe` it finds (checked every poll).

All autonomous work uses the **small CPU model** instead
(`qwen2.5:3b` via Ollama, ~2 GB, `num_thread=4`).

## Running it

```powershell
cd "C:\Users\gamel\OneDrive\Documents\Default Project\Coal\lm_track\coal_chat"
py -3.15 coal_safe_autonomy.py            # start (3.5-day max)
py -3.15 coal_safe_autonomy.py --status   # is it alive? RAM? 35B?
py -3.15 coal_safe_autonomy.py --stop     # ask it to stop
py -3.15 coal_autonomy_report.py          # what did it do while I was away?
```

State lives in `~/.coal/autonomy/`:
`heartbeat`, `safe-autonomy.log`, `supervisor.pid`, `STOP`.

## Safety rules built in

| Rule | Implementation |
|---|---|
| 35B never starts | `CoalO_35B=1` + periodic `kill_35b()` |
| No run when RAM is tight | refuses to run below **5 GB free**; pauses the daemon if it drops |
| User's work wins | everything at **BELOW_NORMAL** priority (daemon + Ollama) |
| No runaway / hung tick | **stall watchdog**: restarts the daemon if no progress for 25 min |
| One daemon at a time | PID file in `governance/`; supervisor relaunches with backoff |
| Bounded logs | log rotation + daemon housekeeping |
| Kill switch | `STOP` file (`--stop`) |
| Time-boxed | exits after `COAL_MAX_HOURS` (default 84 h) |

Tunable via env: `COAL_FLOOR_GB`, `COAL_SUP_POLL`, `COAL_STALL_MIN`,
`COAL_MAX_HOURS`.

## What it does each tick (30 min interval)

`study` (learning cycle) · `observe` (find + ingest a fresh source) ·
`reflect` (measure) · `improve` (self-improvement, validated + rollback) ·
`archive` (fold the queue onto the board).

Disabled on purpose: `practice` and the **mission queue** — those need the
Linux sandbox (WSL), which is not installed, and they would also want the
35B.

## WSL (needs one admin click)

WSL cannot be installed without elevation. When convenient, run **once as
administrator**:

```powershell
powershell -ExecutionPolicy Bypass -File setup_wsl.ps1
```

It enables the features, installs WSL, re-attaches the surviving sandbox
disk (`D:\Coal_SANDBOX\Ubuntu-24.04\ext4.vhdx`) and installs
`iverilog verilator gtkwave`. After that, sandbox builds/missions can be
re-enabled in `config.json` (`governance.run_practice`,
`run_mission_queue`, `run_retry_missions`).

## Monitoring when you return

1. `py -3.15 coal_autonomy_report.py` — one-page summary.
2. `~/.coal/governance/daemon.log` — tick-by-tick results.
3. `~/.coal/governance/telemetry.jsonl` — structured events.
4. `~/.coal/learning/`, `~/.coal/selfimprove/` — what it studied/changed.
