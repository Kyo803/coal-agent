# Coal — COMPANY HANDOVER (READ ME FIRST)

**Audit date:** 2026-10-03 · **Handed over by:** the builder · **For:** the next company/team taking over Coal.

> This folder is the complete, file-by-file audit of the Coal project. Read
> this file first, then the numbered audit documents. Every source file in the
> codebase is documented in one of the `0X-*.md` documents. If you need to know
> *what a file does*, look it up in the **File Map** below and jump to the
> relevant section.

---

## 1. What Coal is

Coal is a **fully local personal AI**: a 35B-parameter brain served by
llama.cpp, wrapped in a custom "body" of forever-memory, a 369-tool layer,
vision, image generation/editing, project awareness, document RAG, and an
autonomous multi-file project builder. Nothing leaves the machine.

Three things are mixed in this repo — all important, all distinguishable:

1. **The Coal assistant runtime** (the product you run): `coal.py`,
   `tools/`, `memory/`, `project/`, `rag.py`, `vision.py`, etc.
2. **The training / research track** (how the brains were made and how to
   make bigger ones): `train_*.py`, `datamix_*.py`, `sft*`, `dpo*`,
   `run_*.py`, `arch*.py`, `gpu/`, `tokenizer*`, checkpoints.
3. **The evaluation / test layer**: `eval/`, `test_tools.py`,
   `test_build.py`, `test_memory.py`, `EVALUATION_REPORT.md`.

Plus **six built example projects** on the Desktop (`Coal Projects/`) that Coal
built autonomously (see `09-BUILT-PROJECTS.md`).

---

## 2. The one-command quick start

```powershell
cd "C:\Users\WERU1\OneDrive\Documents\Default Project\Coal\lm_track\coal_chat"
python install.py            # link model + server into Program Files, write config (first time)
python coal.py                # interactive chat (auto-starts the llama-server)
python coal.py --say "hello"  # one-shot
python coal.py --status       # full status as JSON
```

Install location: `C:\Users\WERU1\AppData\Local\Programs\Coal\`
Codebase root: `C:\Users\WERU1\OneDrive\Documents\Default Project\Coal\lm_track\coal_chat\`

Test suite (should be green):

```powershell
python test_tools.py    # 145 tool-layer tests
python test_build.py    # 38 build-capability tests
python test_memory.py   # persistent-memory gate
python eval/suite.py --scale quick --llm none
```

---

## 3. FILE MAP (index — jump to the section for details)

| Area | Files | Audit doc |
|------|-------|-----------|
| Entry point / CLI | `coal.py` | `03-RUNTIME-CORE-AUDIT.md` |
| Config | `coal_config.py`, install `config.json` | `03-…`, `08-…` |
| Server lifecycle | `server_manager.py`, `start_coal_server.bat` | `03-…` |
| Model backends | `coal_backend.py`, `hf_backend.py`, `run_local.py`, `local_run.py` | `03-…`, `07-…` |
| Chat template + streaming | `coal_template.py`, `streaming.py`, `chat.py`, `chat_v2.py` | `03-…` |
| Sessions / personality / router | `session.py`, `personality.py`, `router.py` | `03-…` |
| Vision / images | `vision.py`, `resources.py` | `03-…` |
| RAG / retrieval | `rag.py`, `retrieval.py`, `bigindex.py` | `03-…` |
| Safety / math / observability | `attachments.py`, `observability.py` | `03-…` |
| Language packs + build capabilities | `langpacks.py`, `generate.py` | `03-…` |
| Tool layer | `tools/` (20 files) | `04-TOOLS-LAYER-AUDIT.md` |
| Memory (forever) | `memory/` (9 files) | `05-MEMORY-PROJECT-AUDIT.md` |
| Detective board | `board/` (11 files), `tools/handlers_board.py`, `board_ui.bat` | `05-…` |
| Security + chip | `tools/handlers_security.py`, `tools/handlers_chip.py`, `chip_architect.py`, `project/contract.py` | `04-…`, `07-…` |
| Project awareness | `project/` (5 files) | `05-…` |
| Evaluation | `eval/` (6 files), `test_*.py` | `06-EVAL-TESTING-AUDIT.md` |
| Training / data / models | `train_*.py`, `sft*`, `dpo*`, `run_*.py`, `arch*.py`, `datamix*`, `fetch*`, `gpu/`, tokenizer, checkpoints, `coal_*/` model dirs | `07-TRAINING-PIPELINE-AUDIT.md` |
| Config / data / logs | root `*.json`, `*.jsonl`, `*.log`, `*.ps1`, `*.sh` | `08-CONFIG-DATA-ARTIFACTS.md` |
| Built projects (Desktop) | `Coal Projects/*` | `09-BUILT-PROJECTS.md` |

---

## 4. How to begin (recommended path for the new team)

1. **Read `01-HOW-IT-WAS-BUILT.md`** — the build story, decisions, and why each
   layer exists.
2. **Read `02-ARCHITECTURE.md`** — the turn flow and module relationships.
3. **Run it** (section 2 above) and walk a few turns: memory recall, a tool
   call, an image.
4. **Read the audit docs** in order `03` → `09` as you touch each area.
5. **Run the test suite** to establish a green baseline before changing anything.
6. For the training track, read `07-TRAINING-PIPELINE-AUDIT.md` and
   `gpu/RUNBOOK.md` — everything is CPU-verified and staged, but nothing has
   been run on rented GPUs yet.

**Gotchas to know up front** (details in the docs):

- Hardware is a 24 GB RAM + Radeon RX 570 8 GB box. The 35B runs at ~5.5 tok/s
  with 8 of 40 layers on Vulkan; the RAM headroom is the real win.
- The 35B and the FLUX.2 image model **cannot be resident at the same time** —
  `resources.py` parks the 35B, renders, reloads.
- Embeddings use CPU-only Ollama (`nomic-embed-text`) so it never steals VRAM
  from the 35B (this was a hard-won bug fix — see `05-…`).
- Cloud/SaaS tools (AWS, kubectl, Stripe, etc.) are **honest Tier-2 stubs** by
  design — they say what's missing, never fake success.
- The `coal_500m`, `coal_brain`, `coal_chat`, `coal_kto`, `coal_online_dpo`,
  `coal_orpo` folders are **model checkpoints/weights**, not source.

---

## 5. License / provenance notes

- Model weights: Qwen-based `Coal-35B-A3B-Q4_K_M.gguf` (renamed in-repo;
  GGUF internal metadata still says Qwen — a known cosmetic limitation).
- Image model: FLUX.2 klein 4B Q8_0 (non-commercial terms apply).
- Everything else in the repo was built in-project.

---

_Next: `01-HOW-IT-WAS-BUILT.md`._