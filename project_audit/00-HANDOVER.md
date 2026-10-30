# Coal — Project Audit & Handover

_Generated 2026-09-30. Complete engineering audit for team onboarding,
maintenance, and continued development._

## What Coal is

Coal is a **fully-local personal AI assistant**. A real 35B-class
Mixture-of-Experts language model ("the brain") runs entirely on the
user's machine via llama.cpp, wrapped in a rich body: persistent memory,
adaptive personality, sessions, document RAG, project awareness
(journaling/audit), ~356 permission-gated tools, browser automation,
vision (image understanding), and local image generation (FLUX.2 klein 4B)
with automatic resource switching.

**No cloud. Nothing leaves the machine.** Everything is on-disk under the
install dir and `~/.coal`.

## The two halves of the codebase

| Half | Location | Purpose |
|---|---|---|
| **Runtime assistant** | `lm_track/coal_chat/` | The production assistant: model server, memory, tools, chat, image gen |
| **Training/experimental** | `lm_track/coal_chat/` (train_*, sft*, dpo*, etc.) | From-scratch model training experiments (500M-1B track) |

This audit focuses primarily on the **runtime assistant**, which is the
shipped, working system. The training files are documented in
`08-training-track.md`.

## The core idea (one sentence)

The 35B brain interprets user intent, Coal's body executes it —
memory so it never forgets, tools so it can act, project awareness so it
never hallucinates about code, and resource-switching so it can even
generate images on a 24GB RAM + 8GB VRAM machine.

## Document index

| File | Contents |
|---|---|
| `00-HANDOVER.md` | This file — overview, quick start, system map |
| `01-architecture.md` | System architecture, data flow, turn lifecycle |
| `02-core-runtime.md` | Config, server manager, streaming, chat pipeline |
| `03-memory.md` | Forever memory: SQLite, embeddings, consolidation |
| `04-tools.md` | The ~356-tool layer: registry, permissions, executor, shell gate, intent |
| `05-projects.md` | Project awareness: ledger, journal, audit, context |
| `06-vision-image.md` | Image understanding + FLUX.2 generation + resource swap |
| `07-eval-testing.md` | Eval suite, tests, verification results |
| `08-training-track.md` | The from-scratch 500M-1B training experiments |
| `09-config-operations.md` | Full config reference, install, run, ops, troubleshooting |
| `10-security.md` | Security model: shell gate, permissions, safety, threat model |
| `11-roadmap.md` | Future changes, known gaps, recommended next steps |

## Quick start

```powershell
cd "C:\Users\WERU1\OneDrive\Documents\Default Project\Coal\lm_track\coal_chat"
python install.py --check     # verify install
python coal.py                 # interactive chat (auto-starts server)
python coal.py --show-thinking # stream the model's reasoning
python coal.py --status        # JSON health report
```

## System map (10,000 ft)

```
                ┌─────────────────────────────────────────────┐
                │                 coal.py (Coal)                │
                │   orchestrates one conversational turn      │
                └──────┬──────────┬───────────┬───────────────┘
                       │          │           │
            ┌──────────▼───┐  ┌───▼─────┐  ┌──▼──────────┐
            │  memory/     │  │ tools/  │  │ project/    │
            │  forever     │  │ ~356    │  │ awareness   │
            │  memory      │  │ gated   │  │ journal/audit│
            └──────┬───────┘  └───┬─────┘  └──────┬───────┘
                   │              │               │
        ┌──────────▼──────────────▼───────────────▼─────────┐
        │            llama.cpp (llama-server.exe)           │
        │    Coal-35B-A3B Q4_K_M  +  mmproj (vision)       │
        │    Vulkan GPU offload (-ngl 8), port 1234          │
        └────────────────────────┬──────────────────────────┘
                                 │
        ┌────────────────────────▼──────────────────────────┐
        │   Ollama (CPU-only, on demand)                    │
        │   nomic-embed-text (embeddings) + coaln-3b/7b      │
        └───────────────────────────────────────────────────┘
                                 │
        ┌────────────────────────▼──────────────────────────┐
        │   stable-diffusion.cpp (sd-cli.exe, Vulkan)       │
        │   FLUX.2 klein 4B  → image generation (swap)      │
        └───────────────────────────────────────────────────┘
```

## Hard facts (verified)

- **Model**: Coal-35B-A3B Q4_K_M (19.7 GB), real Qwen3.6-35B-A3B MoE
  (35B total / ~3B active, 40 layers, 256 experts, 8 active)
- **Server**: llama.cpp 2.46.0 Vulkan build, `-ngl 8` layers on an
  8 GB Radeon RX 570, 8192 ctx
- **RAM**: 24 GB total — the tightest constraint in the system
- **Memory**: SQLite (`~/.coal/memory.db`) + nomic 768-d embeddings
  (Ollama, CPU-only to avoid VRAM theft)
- **Tools**: 358 registered across 14 categories
- **Tests**: 145 tool tests, 15-module regression, 450K deterministic
  eval cases at 100%
- **Image gen**: FLUX.2 klein 4B Q8_0, 1024×1024, ~2.5-4 min on RX 570
- **Image edit**: FLUX.2 klein reference/init modes (`edit_image`)
- **Custom images**: user specs → subject/style/mood/color/ratio → `custom_image`
- **Web search**: pure-urllib Bing fallback (no ddgs needed)

## Ownership / handover notes

- Everything is local and self-contained; no external services required
  beyond the model files (one-time downloads).
- The system is **proven working end-to-end**: chat, memory recall,
  file/project creation with journaling, image generation + swap.
- Known constraints are honest and documented in `11-roadmap.md`.