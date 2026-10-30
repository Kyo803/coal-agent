# 02 — Core Runtime

## `coal_config.py` — single source of config

Every module imports the shared `cfg` object from here. It reads
`config.json` from the install dir, applies defaults, and honors env
overrides.

**Key behavior:**
- `SEARCH_PATHS`: `COAL_CONFIG` env → `%LOCALAPPDATA%\Programs\Coal\config.json` → local `config.json`
- Attribute access: `cfg.model.gguf`, `cfg.memory.root` (auto-expands `~`)
- Properties: `cfg.base_url` (`http://host:port/v1`), `cfg.memory_root`, `cfg.rag_root`
- Path helpers: `cfg.model_path()`, `cfg.server_path()`, `cfg.mmproj_path()`
- Env overrides: `COAL_PORT`, `COAL_MODEL`, `COAL_CONFIG`
- `cfg.report()` → human/JSON status summary

**Important**: `cfg` is a `_Section` dict subclass, so `cfg.get("image", {})`
and `cfg.image.width` both work.

## `server_manager.py` — model server lifecycle

Manages the llama.cpp server that serves the 35B.

| Method | Purpose |
|---|---|
| `health()` | GET `/models` → is the server answering |
| `is_running()` | is a llama-server process alive |
| `start(gpu_layers, wait)` | launch server; auto-step GPU layers down on OOM |
| `stop()` | kill llama-server (used by image swap) |
| `ensure()` | start if not healthy |
| `restart()` | stop + start |
| `status()` | running/healthy/model/URL/free-RAM/log path |

**Critical guards (learned from real incidents):**
- **RAM guard**: requires `min_free_ram_gb` (default 3.0) free before start — llama.cpp mmaps the GGUF, so only the working set must be resident.
- **Duplicate-server guard**: if a llama-server process exists but isn't HTTP-healthy yet (still loading), wait up to 60s for it rather than starting a second. *Two servers = 2× VRAM = OOM* (this was a real bug).
- **GPU auto-tune**: on `failed to allocate` / `OutOfDeviceMemory`, halve `gpu_layers` and retry; eventually CPU-only.

**Server launch flags** (from `start()`):
```
llama-server.exe -m <model> --host 127.0.0.1 --port 1234 -c 8192
  -ngl <layers> -t <threads> --no-webui
  --mmproj <mmproj> --image-min-tokens 1024   (vision)
```

**Measured GPU layer ceiling** (RX 570 8 GB): 8 layers at 8192 ctx is
reliable; 10 marginal; 12+ OOM. `config.json` uses `gpu_layers: 8`.

## `streaming.py` — SSE streaming client

`stream_chat(messages, ...)` posts to `/chat/completions` with
`stream: true` and reads the SSE stream, returning
`(content, tool_calls, reasoning)`.

- **Live tokens**: `on_token` callback (prints as they arrive)
- **Live reasoning**: `on_thinking` callback + the `reasoning_content`
  field (Qwen's native reasoning channel) is captured separately and
  returned as the third element — this is how "show what it's thinking"
  works, and how file-content generation captures code that the model
  puts in reasoning.
- **Tool calls**: streamed tool_call fragments are accumulated
  (name arrives once, args appended), normalized from JSON strings.
- **XML fallback**: if no OpenAI tool_calls, parse raw
  `<tool_call><function=...>` XML from content.
- **tool_choice**: optional `{"type":"function","function":{"name":X}}`
  to force a specific tool (used by intent-first path).
- **max_tokens / temperature** pass-through; write path uses 4096.

## `coal_template.py` — chat template + tool parsing

- `IM_START` / `IM_END` — `<|im_start|>` template markers
- `TOOL_SCHEMAS` — OpenAI function schemas for memory/document tools
- `parse_tool_calls(text)` — parse raw XML `<tool_call>` blocks
- `split_thinking(text)` — split ` thinking ... response` in content
- `format_tool_response(result)` — wrap a tool result in `<tool_response>`
- `render_chat(...)` — manual template render (for non-server paths)
- `BASE_SYSTEM` — base persona (personality.py adapts it)

## `coal_backend.py` — endpoint autodetect

`autodetect()` probes local OpenAI-compatible endpoints (the llama.cpp
server first, then Ollama) and picks the highest-preference model
(`PREFERENCE` = roxn-35b > roxn-7b > coaln-3b ...). `CoalBackend` is a
minimal client used by eval/chat_v2.

## `personality.py` — adaptive traits

Traits in [0,1]: warmth, directness, humor, formality, verbosity.

- `observe(user_text)` — EMA-drifts traits toward the user's measured
  style (word count, formality markers, humor/emoji, casual slang)
- Persists to `~/.coal/personality.json`
- `describe()` → "friendly, very direct, casual, brief"
- `system_prompt(extra_context)` — builds the system prompt from
  traits + learned style notes + memory/project context

## `session.py` — conversation persistence

- Sessions are JSON files under `~/.coal/sessions/`
- `add`, `save`, `resume(name)`, `latest()`, `list_sessions()`
- `messages(limit)` → for the model
- `export_markdown()` → readable chat log

## `router.py` — classification + thinking

`classify()` → `simple | coding | reasoning | arithmetic | chat | vision`
`route()` → model + base_url + `thinking` flag. Defaults route everything
to the 35B; the Ollama fast path is only used when explicitly enabled.

## `attachments.py` — safety + calculator + TME

- `lockout_check(text)` — crisis-phrase detection → hard redirect
- `tool_gate(text)` — sandboxed AST calculator for arithmetic spans
- `TurnMemory` — TME turn compression (keep high-S, compress low-S)

## `coal.py` CLI

```
python coal.py                     # interactive
python coal.py --say "hi"          # one-shot
python coal.py --status            # JSON report
python coal.py --session work      # named session
python coal.py --show-thinking     # stream reasoning live
python coal.py --no-autostart      # don't start the server
```

`chat_loop` prints streamed tokens, and if a turn returned a plain-string
answer (calculator, image gen, tool results, project actions) it prints
that directly (fixed bug: previously those were silently dropped).