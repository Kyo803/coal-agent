# Coal - Local Run Guide

Everything runs on your machine. No cloud. Your Qwen3.6-35B-A3B brain,
your Coal memory, your data.

## Your setup (verified)

- **Model:** `Qwen3.6-35B-A3B-Q4_K_M.gguf` (19.7 GB)
  at `C:\Users\WERU1\.lmstudio\models\lmstudio-community\Qwen3.6-35B-A3B-GGUF\`
- **Server:** LM Studio's bundled `llama-server.exe` (Vulkan/CPU)
- **Hardware:** 24GB RAM + Radeon RX 570 (8GB, Vulkan)
- Runs CPU-only (Vulkan buffer allocation fails under the display); ~40s
  per reply. The 3B/7B models in Ollama are faster if you want speed.

## Start the model server

```powershell
cd "C:\Users\WERU1\OneDrive\Documents\Default Project\Coal\agent"
cmd /c "start /b start_qwen_server.bat"
```

Wait ~3 minutes for the 19.7GB model to load. Verify:

```powershell
curl http://localhost:1234/v1/models
```

## Talk to Coal

```powershell
python run_local.py
```

It auto-detects the server and uses the best model. Or force it:

```powershell
python run_local.py --backend qwen
```

## What was measured on your machine

| Test | Qwen3.6-35B-A3B + Coal | 135M baseline |
|------|------------------------|---------------|
| QA factuality | **8/8 = 1.00** | 0.49 |
| Multi-turn memory recall | **3/3 = 1.00** | 0.28 |
| Deterministic features (450K cases) | 1.00 | 1.00 |

Memory recall works: tell it "my name is WERU, I'm building a robot arm
with NEMA 23 motors", then ask "what is my name?" -> "Your name is WERU."

## How memory works (direct tool calls)

The 35B model calls Coal's memory tools **natively** (function calling):
- `search_memory` - recall past conversations/facts
- `remember` - store a fact
- `update_profile` - update your profile
- `forget` - delete memories

No fine-tuning needed; the model decides when to call them.

## Backends (auto-detected)

| Priority | Endpoint | Models |
|----------|----------|--------|
| 1 | LM Studio `localhost:1234` | Qwen3.6-35B-A3B, Gemma 4 31B/12B QAT |
| 2 | Ollama `localhost:11434` | qwen2.5:7b, qwen2.5:3b, llava:7b |
| 3 | `--backend hf` | small HuggingFace fallback |
| 4 | `--backend v2` | our from-scratch 500M (FOU/EME/PLHE) |

## Where memory lives

`~/.coal/` - `memory.db`, `vectors/`, `profile.json`. Delete to wipe.
Nothing leaves your machine.

## Evaluate

```powershell
python eval_live.py --n 12          # real model, QA + multi-turn
python eval/suite.py --scale huge --llm none   # 450K deterministic
python eval/suite.py --scale quick --llm qwen --llm-count 8
```

## Speed tips

- 35B CPU-only: ~40s/reply. For snappier chat, load the **Gemma 4 12B
  QAT** or **qwen2.5:7b** instead (edit `start_qwen_server.bat` model path,
  or just let Ollama serve them).
- Keep context (`-c`) small (4096) to limit RAM.
