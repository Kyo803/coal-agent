# 09 — Configuration, Install, Run, Operations

## The install layout

```
C:\Users\WERU1\AppData\Local\Programs\Coal\
  config.json                     central config
  models\
    Coal-35B-A3B-Q4_K_M.gguf     19.7 GB  (the brain)
    Coal-35B-A3B-mmproj-BF16.gguf 0.84 GB (vision projector)
  server\
    llama-server.exe              llama.cpp 2.46.0 Vulkan build
    ggml-*.dll                    (Vulkan + CPU backends)
    fallback\                     older Vulkan build for recovery
  image\
    sd-cli.exe, sd-server.exe     stable-diffusion.cpp (win-vulkan)
    ggml-vulkan.dll, ggml-*.dll
    models\  flux-2-klein-4b-Q8_0.gguf, Qwen3-4B-Q4_K_M.gguf,
             flux2_vae.safetensors
    out\     image-generation output scratch
  logs\
    llama_server.log              server log
    coal.jsonl                     observability log
    *.log                         tuning/benchmark logs
```

## Install / verify

```powershell
cd "C:\Users\WERU1\OneDrive\Documents\Default Project\Coal\agent"
python install.py            # idempotent: link model+server, write config
python install.py --check    # verify model/server/mmproj paths
```

`install.py`:
- Search paths: the install `models\` (first) then `C:\Models`
- Links model files under the Coal name (source name never revealed)
- Copies the server exe + DLLs
- Writes `config.json`

## Config reference (`config.json`)

### `model`
- `gguf`, `mmproj`, `server_exe` — absolute paths
- `host` (127.0.0.1), `port` (1234), `context` (8192)
- `gpu_layers` (8) — Vulkan layers; `vram_reserve_gb` (0.8)
- `vulkan_stepdown` (true) — auto-step on OOM
- `threads` (8), `thinking` (false), `vision` (true)
- `max_tokens` (1024), `temperature` (0.6)

### `fallback_servers`
- Ollama endpoint + `roxn-7b` (the renamed fast fallback model)

### `memory`
- `root` (~/.coal), `embed_backend` (ollama), `embed_model`
  (nomic-embed-text), `ollama_url`, `consolidate_every` (8),
  `recall_k` (8)

### `personality`
- `name` (Coal), `adapt_to_user`, `base_traits` (warmth/directness/
  humor/formality/verbosity)

### `rag`
- `watch_dirs`, `index_path`, `chunk_chars` (800)

### `tools`
- `workspace` (~/.coal/work)
- `enabled` — 10 categories (filesystem, search, execution, git, web,
  database, orchestration, output, system, project)
- `auto_allow` — Tier-1 read/search tools that never prompt
- `allow_tier2`, `ask_confirms`

### `project`
- `source_root` (Desktop), `ledger_root` (~/.coal/projects),
  `journal_every_write`

### `image`
- `model` (flux2-klein-4b), `backend` (vulkan0), `steps` (4),
  `width`/`height` (1024), `timeout` (900)

### `observability`
- `log_dir`, `log_level`, `trace_tools`

## Run commands

```powershell
python coal.py                     # interactive
python coal.py --show-thinking     # stream reasoning
python coal.py --say "hi"          # one-shot
python coal.py --status            # JSON report
python coal.py --session name      # named/resumed session
python coal.py --no-autostart      # skip server start
```

Also: `start_coal_server.bat` — start the model server standalone.

## Process layout when running

| Process | Port | Purpose |
|---|---|---|
| `llama-server.exe` | 1234 | the 35B brain (Vulkan, -ngl 8) |
| `ollama.exe` (+ runner) | 11434 | embeddings + fallback models (CPU-only) |
| `sd-cli.exe` | — | spawned only during an image swap |

## The `~/.coal` data dir

```
memory.db / -shm / -wal   SQLite (sessions, messages, facts, entities)
vectors/                  embedding .npy + ids
profile.json              user profile
personality.json          adaptive traits
sessions/                 conversation JSON
rag/                      document index
work/                     workspace (files + generated images)
projects/                 per-project ledger + journal
ollama.log                CPU-only Ollama startup log
```

## Operations / troubleshooting

| Symptom | Cause / fix |
|---|---|
| Empty replies | Two llama-servers = 2× VRAM (fixed by duplicate guard). Or Ollama stole VRAM → embeddings run CPU-only now. Restart `python coal.py`. |
| HTTP 500, `ErrorOutOfDeviceMemory` | VRAM exhausted. Check only ONE llama-server is running; `-ngl 8` is the safe max. |
| Vector-index crash (dim mismatch) | Fixed: `index.add()` self-heals on embedding-space change. |
| `ValueError: size 768 vs 0` | Fixed: `embed()` never returns a 0-length vector. |
| Image reply blank | Fixed: `chat_loop` now prints non-streamed answers. |
| Slow chat | 35B CPU-bound. `--show-thinking` shows it's working. Consider Ollama fast path. |
| VRAM "0%" | Task Manager shows the 3D engine; Vulkan compute shows under compute engine. It IS working. |
| "I am Qwen" | Model weights self-identify; file/code/doc traces are all rebranded to Coal. |

## Benchmark results (measured)

- 35B Q4_K_M: ~5.5-7 tok/s (Vulkan 8 layers) vs 5.9 (CPU-only)
- Free RAM at launch: ~9-10 GB (Vulkan) vs 0.5 GB (CPU-only)
- Image gen: 512 ≈ 48s · 1024 ≈ 2.5-4 min (RX 570)
- GPU layer ceiling: 8 reliable, 10 marginal, 12+ OOM at 8192 ctx