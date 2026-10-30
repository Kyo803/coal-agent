# 01 — System Architecture & Data Flow

## Overview

Coal is a layered system. Each layer has a single responsibility and a
well-defined interface:

```
Layer 0: Model inference  -> llama.cpp server (OpenAI-compatible API)
Layer 1: Client           -> streaming.py (SSE), vision.py, coal_backend.py
Layer 2: Cognition        -> coal.py respond() pipeline
Layer 3: Memory           -> memory/ package (SQLite + vectors)
Layer 4: Action           -> tools/ package (registry, executor, gate)
Layer 5: Context          -> project/ package (ledger, journal, audit)
Layer 6: Coordination     -> resources.py (image-gen swap), server_manager
Layer 7: Observability    -> observability.py (JSONL)
```

## One turn, from input to answer

The `Coal.respond(user_text)` method is the heart. Every turn follows this
exact order:

```
1. SAFETY       attachments.lockout_check -> crisis phrases? hard redirect
2. CALCULATOR   attachments.tool_gate     -> arithmetic span? verified answer
3. ROUTE        router.route()            -> kind (simple/coding/reasoning/chat)
4. MEMORY       memory.assemble()         -> profile + facts + past turns
5. RAG          rag.context()             -> doc passages if any
6. PROJECT      project_context()         -> architecture map if project open
7. PERSONALITY  personality.system_prompt() -> adapted system prompt
8. INTENT       tools.intent.detect_intent() -> which SPECIFIC tool to force
9. TOOLS        lazy_schemas()            -> load the right category's schemas
10. GENERATE    stream_chat()             -> SSE, live tokens + reasoning
11. EXECUTE     tool loop (up to 4 rounds)-> run tools, feed results back
12. RECORD      memory.add_turn() + session + observability
```

## Intent-first decision (the key innovation)

Instead of relying on the model to choose tools (which it often skips),
Coal **detects the user's purpose first** (`tools/intent.py`), and if
confident, **forces** the exact tool call:

- "make me a snake game" -> force `write_file`
- "make me an image of a dragon" -> force `generate_image`
- "check the files in my workspace" -> force `glob`
- "read my snake.html" -> force `read_file`
- "create a project for X" -> force `project_new`
- "remember that I like dark mode" -> force `remember`

High-confidence intents also guarantee the tool's schema is loaded
(`lazy_schemas(ensure=...)`), and the forced tool is executed with real
data fed back to the model for a grounded answer.

## The tool loop

For non-forced turns, the model may emit tool calls (OpenAI format,
normalized by the server). Coal:

1. streams until the model returns `tool_calls` or text
2. appends the assistant message
3. executes each tool via `_run_tool` (native) or `ToolExecutor` (safe)
4. appends the `<tool_response>` back into messages
5. loops (max 4 rounds) until the model answers with text

## Memory + context budget

Context is assembled within a token budget (`memory/assemble.py`), in
priority order: profile → facts → episodic → working tail. This keeps the
35B's 8K context from being flooded by everything ever said.

## Image generation (resource swap)

When intent = `generate_image`, Coal must run a *second* heavy model
(FLUX.2 klein) that won't fit alongside the 35B in 24 GB RAM. So it
**time-slices**:

```
detect "make an image..." -> generate_image
  resources.swap_for_image():
    1. server_manager.stop()      # park 35B, free ~10-15GB RAM + 8GB VRAM
    2. wait for free RAM >= 6GB
    3. sd-cli (Vulkan + offload)  # generate PNG (~2.5-4 min @ 1024)
    4. server_manager.ensure()    # reload the 35B
  -> image saved to project images\ or workspace, journaled
```

Everything else (memory/personality/session) is on disk, so parking the
server loses nothing.

## File map (runtime)

| Path | Role |
|---|---|
| `coal.py` | Unified assistant class + CLI (`Coal`) |
| `coal_config.py` | Config loader (`cfg`), env overrides |
| `server_manager.py` | llama.cpp server lifecycle + RAM/VRAM guards |
| `streaming.py` | SSE streaming client (`stream_chat`) |
| `coal_template.py` | Chat template + tool XML parsing |
| `coal_backend.py` | Autodetect/score local model endpoints |
| `personality.py` | Adaptive traits + system prompt |
| `session.py` | Save/resume/export conversations |
| `vision.py` | Send images to the model (mmproj) |
| `rag.py` | Document ingestion + retrieval |
| `router.py` | Task classification + thinking control |
| `observability.py` | JSONL logs + stats |
| `attachments.py` | Safety lockout, calculator gate, TME |
| `resources.py` | Image-gen resource swap |
| `install.py` | Idempotent installer + config writer |
| `memory/` | Store, Embedder, VectorIndex, Retriever, Consolidator, Profile, Assembler, MemoryTools |
| `tools/` | specs, permissions, exec, shell, shell_gate, intent, handlers_* |
| `project/` | project, journal, audit, context |
| `eval/` | suite, generators, runners, metrics, final_report |
| `test_tools.py` | 126 tool-layer tests |
| `test_memory.py` | Memory gate |
| `BACKLOG.md` | Saved roadmap notes |

## Process layout (running system)

- `llama-server.exe` — the 35B brain, port 1234 (Vulkan, `-ngl 8`)
- `ollama.exe` — embeddings + small fallback models, port 11434 (CPU-only)
- `sd-cli.exe` — image generation (only during a swap, spawned/stopped)
- Coal is a single Python process wrapping all of the above.