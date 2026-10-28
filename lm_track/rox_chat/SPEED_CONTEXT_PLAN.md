# ROX N — Speed & Context Upgrade (Phase 0) — EXECUTED

Status: **Phase 0 complete.** Server: bundled `llama-server`
**v0.5.0-dev (commit a25c986)**.
Hardware: 23.9 GB RAM; 6 cores / 12 threads; Radeon RX 570 (WMI reports 4 GB).

## Results

| Item | Before | After |
|---|---|---|
| Effective context | 8,192 | **16,384** (`n_ctx_slot=16384`) |
| KV cache | f16 | **q8_0** (`-ctk q8_0 -ctv q8_0`) |
| Flash attention | auto/off | **`-fa on`** |
| Prompt cache | — | `--cache-reuse 256`* |
| Free RAM (35B resident) | ~1.9 GB | **~10 GB** |
| Tok/s (single stream) | 6.95 | ~6.1–6.8 (neutral; ±15% variance) |
| Speculative decoding | — | **not viable (disabled)** — see below |

\* `--cache-reuse` is auto-disabled by llama.cpp when a multimodal `mmproj`
is loaded ("cache_reuse is not supported by multimodal"). Kept for
text-only launches.

## Speculative decoding — investigated, not usable here

1. The 35B tokenizer is **Qwen3.6** (`architecture=qwen35moe`,
   `tokenizer.ggml.pre=qwen35`, **vocab = 248,320**, merges 247,587,
   eos 248,046). The planned **Qwen3-0.6B draft (vocab 151,936) is
   incompatible.**
2. A vocabulary-compatible draft exists: **`Qwen/Qwen3.5-0.8B`** (vocab
   248,320, same `qwen35` pre-tokenizer). Downloaded
   `Qwen_Qwen3.5-0.8B-Q4_K_M.gguf` (0.55 GB) to
   `Programs\ROX N\models\drafts\`.
3. With `-md <0.8B> --spec-type draft-simple`, the server loads, but
   generation **drops to ~2.1 tok/s** — the 0.8B draft occupies the same 8
   CPU threads and dominates. Net loss.
4. `--spec-type draft-mtp` (self-speculation) fails: the 35B **GGUF contains
   no MTP layers** ("context type MTP requested but model doesn't contain
   MTP layers"), despite `mtp_num_hidden_layers: 1` in the HF config.
5. Threads 12 gave no gain over 8 (CPU-bound).

**Decision:** speculative decoding disabled (`draft_gguf=""`, `spec_type=""`).
The draft GGUF remains on disk for future use (e.g. a stronger CPU/GPU).

## Config keys added (`config.json` + `rox_config.py`)

```jsonc
"context": 16384,
"flash_attn": true,
"kv_type_k": "q8_0",
"kv_type_v": "q8_0",
"cache_reuse": 256,
"n_cpu_moe": 0,
"draft_gguf": "",            // set to a same-tokenizer GGUF to enable
"spec_type": "",             // "draft-simple" | "draft-mtp" | ...
"spec_draft_n_max": 16,
"spec_draft_n_min": 0,
"draft_gpu_layers": 0,
"draft_kv_type_k": "q8_0",
"draft_kv_type_v": "q8_0"
```

`server_manager._speed_args()` emits these conditionally. `rox_config` adds
`cfg.draft_path()` and the new defaults.

## Regression

`test_tools` 145/0, `test_security` 16/0, `test_chip` 9/0, `test_board`
31/0. Live generation verified at 16K.

## Next speed levers (deferred)

- GPU offload tuning (`-ngl`) if VRAM allows more than 8 layers.
- A future draft on a stronger machine (the 0.8B is ready).
- QLoRA custom brain — see Phase 4 below.

---

## Later phases (unchanged)

### Builder upgrade (CPU-class correctness)
Generate ONE module -> `iverilog -t null` -> retry that file until it parses;
freeze parsed modules (hash); cap file size (~4 KB); surgically patch the
failing construct instead of regenerating whole files.

### Custom brain on a small rental ($10-15)
1. QLoRA a small draft to the domain.
2. QLoRA a 7B (`roxn-7b`) from its HF source.
3. QLoRA the 35B (4-bit) if a 24-48 GB card is available
   (HF source at `D:\ROX_N_HF\Qwen3.6-35B-A3B`).
