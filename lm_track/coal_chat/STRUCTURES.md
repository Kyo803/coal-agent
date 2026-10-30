# Coal — 3 Core Structures (MoE · Memory · Task Router)

Implemented from the actual 35B-A3B model files in our hands.

## 1. MoE Expert Engine (`moe/`)
The 35B is `Qwen3_5Moe`: **256 experts / 8 active**, shared-expert 512,
hybrid (30 Gated-DeltaNet linear-attn + 10 full-attn), MTP-1, native
262K ctx. The GGUF inventory:

| part | GB | share |
|---|---|---|
| **experts** (256 × up/gate/down) | **19.50** | 92% |
| shared expert | 0.08 | 0.4% |
| dense (attn + deltanet + embd + output + routers) | 1.58 | 7.4% |

Tools: `moe/inventory.py` (manifest), `moe/placement.py` (expert paging via
`-ot ...=Vulkan0`, experts stay CPU/mmap), `moe/presets.py` (profiles +
`presets.apply(name)`), `moe/bench.py` (before/after harness). Server reads
`model.extra_args`/`gpu_layers` set by a profile.

### Measured (real, not projected)
| profile | config | tok/s | RSS | free RAM |
|---|---|---|---|---|
| chat | `-ngl 8` (current default) | **5.9–6.6** | ~15.0 GB | ~0.4–1.6 GB |
| moe_resident | `-ngl 0` + dense→Vulkan0 | 2.7 | ~13.5 GB | ~0.3 GB |
| cpu | `-ngl 0` | 2.2 | ~13.9 GB | ~0.4 GB |

**Honest conclusion:** on this Polaris GPU the 8-layer `-ngl 8` config wins;
full dense-GPU offload doesn't beat it here (float32 deltanet + weak GPU).
Expert paging trims ~1.5–2 GB RSS. The biggest throughput lever remains the
pipeline change (thinking-off turned generation from 147 s → 4.3 s per
file, ~34×).

## 2. Memory Mediator (`memory/mediator.py`)
Arbiter for the 24 GB crunch: measures free RAM, server RSS, Ollama-loaded
models; advisory `plan(phase)` and safe `apply()` (can park Ollama, never
kills the 35B). Config: `memory.min_headroom_gb`, etc.

## 3. Task-Specialization Router (`router/`)
Families (chip/code/long_doc/chat) → serving profile + **domain overlay** +
**verifier mode**. `builder.generate_mission` injects the chip overlay and
now gates every leaf RTL module with a **per-module behavior testbench**
(`builder/hdl_tb.py`): deterministic wiring header + model-filled stimulus,
compiled with `-s tb_<mod>`, must print `<MOD>:PASS` before the module is
frozen/trusted. Plus `_hdl_patch` (module-name), `_cpp_patch` (Makefile),
port-conformance `hdl_verify`.

## Verified
`test_moe` 14, `test_router` 12, `test_memory_engine` 7, `test_mission` 15,
`test_builder` 20, `test_tools` 145 — all green (plus autonomy/governance/
finetune).

## Status / next — pending items done
- **Behavior-TB gate proven live**: it *caught a genuinely non-compliant*
  generated RAM (byte-enable semantics wrong) and rejected it | we verified
  the check macro→task fix and cause classification (behavior vs tb error).
- **MERIDIAN-16 is green through the gate** via the **library fallback**
  (reference `mem64k.v` + `tb_mem.v` in `missions/refs/`): compiled ✅,
  tested ✅ (`MERIDIAN:PASS`), port-verified ✅. The builder now supports
  `"reference"` per unit — the escalation ladder made concrete.
- **Overnight grind wired**: daemon gains `mission_retry` (night task) that
  re-attempts unresolved missions (`governance.run_retry_missions`,
  `night_retries`).
- **Verilog SFT corpus seeding**: `finetune.verilog_export()` mines gated
  RTL → chat pairs for the QLoRA'd drafter (2 pairs so far from meridian).

## Remaining (honest)
- Default server profile = `chat` (best measured). `presets.apply` switches
  (requires restart).
- HELIOS-16's full overnight drive runs via the daemon at night now; a live
  single-run on this saturated machine isn't guaranteed green — that's what
  the grind + QLoRA drafter are for.