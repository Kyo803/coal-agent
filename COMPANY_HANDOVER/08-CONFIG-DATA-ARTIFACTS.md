# 08 — CONFIG, DATA FILES, LOGS, AND ARTIFACTS

The non-source files that matter: configuration, staged data, generated data,
logs, install layout, and the `~/.rox` runtime store.

---

## 1. Configuration

| File | Purpose |
|------|---------|
| `rox_config.py` (in `03-…`) | Loads the config below. |
| `C:\Users\WERU1\AppData\Local\Programs\ROX N\config.json` | **THE config.** Sections: `model` (name `ROX-N-35B-A3B`, gguf + mmproj paths, server_exe, host 127.0.0.1, port 1234, context 8192, gpu_layers 8, vram_reserve_gb, vulkan_stepdown, threads, thinking, vision, max_tokens, temperature), `fallback_servers` (Ollama `roxn-7b`), `memory` (root `~/.rox`, embed_backend ollama, embed_model nomic-embed-text, max_facts, consolidate_every, recall_k), `personality` (name Rox, adapt_to_user, base_traits), `tools` (enabled/auto_allow/allow_tier2/ask_confirms), `project`, `board` (model `roxn-3b`, ollama_url, idle_seconds, auto_archive, park_35b, provenance, num_ctx, budget_tokens), `image` (model, backend, steps), `rag`. |
| `str_config.json` | STR trigger calibration (θ1 threshold 0.4896, dis 0.5, recall targets). Consumed by `retrieval.py`/`calibrate.py`. |
| `data_manifest.json` | 100B data manifest: target_tokens, mix ratios (web/code/math/conversation/instruction), per-kind token budgets. |
| `stage0.json` | Stage-0 mechanism-compose results. |
| `fim.json` | FIM gradient-conflict scores. |
| `matrix.json` | Mechanism-ablation results. |
| `model_compare.json` | Base vs SFT vs KTO … on 36-QA (accuracy + identity). |
| `brain_eval.json` | Base vs our SFT `rox_brain` on 36-QA. |
| `evals.json` | Evaluation gate outputs (factuality, coherence, fallbacks). |
| `eval_results.json` | Full suite results (input to `eval/final_report.py`). |
| `bpe_demo.json` | BPE demo merges (tiny tokenizer demo). |

## 2. Staged data (`data_fresh/`)

Fetched conversational + English-teaching corpora (raw, staged for tokenizing).
`fetch_report.json` = fetch summary. The `.jsonl` files (sizes shown):

| File | Size | Content |
|------|------|---------|
| `data_fresh/fineweb_edu.jsonl` | 3.0 GB | FineWeb-Edu (English teaching). |
| `data_fresh/openwebtext.jsonl` | 3.0 GB | OpenWebText. |
| `data_fresh/wildchat.jsonl` | 2.8 GB | WildChat (multilingual conversations). |
| `data_fresh/openhermes.jsonl` | 0.97 GB | OpenHermes instructions. |
| `data_fresh/soda.jsonl` | 0.75 GB | SODA dialogues. |
| `data_fresh/ultrachat.jsonl` | 0.61 GB | UltraChat. |
| `data_fresh/slimorca.jsonl` | 0.54 GB | SlimOrca. |
| `data_fresh/shp.jsonl` | 0.42 GB | SHP (web feedback). |
| `data_fresh/orca_math.jsonl` | 0.18 GB | Orca-Math. |
| `data_fresh/hh_rlhf.jsonl` | 0.15 GB | HH-RLHF. |
| `data_fresh/oasst2.jsonl` | 0.095 GB | OASST2. |
| `data_fresh/oasst1.jsonl` | 0.056 GB | OASST1. |
| `data_fresh/ultrafeedback.jsonl` | 0.039 GB | UltraFeedback. |
| `data_fresh/no_robots.jsonl` | 3.6 MB | No-Robots instructions. |
| `data_fresh/fetch_report.json` | — | Fetch summary. |

## 3. Generated data at root

| File | Size | Content |
|------|------|---------|
| `dpo_prefs.jsonl` | 119.6 MB | DPO preference pairs. |
| `sft_train.jsonl` | 9.3 MB | SFT training set (mined dialogue). |
| `sft_val.jsonl` | 0.5 MB | SFT validation set. |
| `persona_prefs.json` | 2 KB | Identity/grounding preference pairs. |

## 4. Logs (runtime + training scratch)

| File | Purpose |
|------|---------|
| `overnight.log` (16.3 KB) | Overnight run output. |
| `pretrain_log.txt` (13.8 KB) | Pretrain run log. |
| `train_log.txt` (18.6 KB) | Training log. |
| `dpo_out.log`, `dpo_err.log`, `dpo_run.err.log`, `train_run.log`, `train_run.err.log` | Alignment/training stderr/stdout scratch. |
| `C:\…\ROX N\logs\llama_server.log`, `rox.jsonl` | Server log + runtime session log (install dir). |

## 5. Scripts (PowerShell / batch)

| File | Purpose |
|------|---------|
| `start_rox_server.bat` | Detached llama-server launch. |
| `train_all.ps1` | Run the full training sequence. |
| `overnight.ps1` | Overnight automation. |
| `pretrain_watch.ps1` | Watch pretrain progress. |
| `dpo_watch.ps1` | Watch DPO progress. |

## 6. Install directory layout (`C:\Users\WERU1\AppData\Local\Programs\ROX N\`)

```
config.json          ← the config (see §1)
models\              ROX-N-35B-A3B-Q4_K_M.gguf (19.7 GB) + mmproj (vision)
server\              llama-server.exe (llama.cpp 2.46.0) + fallback\ (2.31.2)
image\               sd-cli.exe + FLUX.2 klein 4B Q8_0 + Qwen3-4B encoder + VAE
logs\                llama_server.log, rox.jsonl
```

**HF source (separate, weight-level):** `D:\ROX_N_HF\Qwen3.6-35B-A3B\` (~67 GB)
— config.json, tokenizer.json, 26 model.safetensors shards of the text backbone
of `Qwen/Qwen3.6-35B-A3B`. Recorded in `config.json` → `model.hf_source` /
`model.hf_repos`. GGUF = serving artifact; HF = source for weight surgery
(abliteration / LoRA / merge / re-quantize), which needs ≥ 70 GB RAM/VRAM.

## 7. `~/.rox/` — the runtime store (created on first run)

```
memory.db       SQLite: sessions, messages, facts, entities, summaries
board.db        detective board: nodes, edges, dossiers, events, provenance, FTS
board_queue.jsonl  exchanges awaiting the archivist
vectors/        nomic-embed-text embeddings (768-d)
profile.json    user profile
personality.json adapted traits
rag/            document index
sessions/       conversation files
projects/       per-project ledgers/journals
langpacks/      installed language packs (typescript, react, tailwind, vite, verilog)
backups/        self-modification backups (edit_self)
work/           default workspace + generated images
```

**Delete `~/.rox` to wipe everything** (memory, profile, RAG, sessions).

---

_Next: `09-BUILT-PROJECTS.md`._