# ROX-N-35B-A3B — Model Card

**Identity:** `ROX-N-35B-A3B-ROXN` — a **ROX N branded build** of the open
`Qwen/Qwen3.6-35B-A3B` weights.

## Provenance (honest)
- **Base:** `Qwen/Qwen3.6-35B-A3B` by Alibaba/Qwen, **Apache-2.0**.
- **Weights:** **bit-identical to the base** (copied verbatim during the
  brand rebuild). No retraining, no fine-tuning, no weight edits — *same
  model, same power*.
- **What ROX N changes:** model metadata identity (name/author/license/
  base-model/tags), plus the entire serving stack, tooling, memory/MoE
  engineering, autonomy and the Silicon Lab pipeline around it.
- **Build tool:** `moe/forge_brand.py` (raw GGUF header rewrite).

## Fingerprints
- Source GGUF SHA-256: `4ac6a06bce551257267f49ad2226f8671a22519ccc1a4dde9d5b433d1f2a410d`
- ROX N build SHA-256: `a7397f03c5201827bf7237ecf2a4e4f393e58323e555d443abab2123e8bf7bb1`
- Quantization: Q4_K_M · Size: 21,166,758,368 bytes

## Architecture (from base)
Qwen3.5/3.6 MoE (`qwen35moe`): 40 layers, **256 experts / 8 active**,
shared expert 512, hybrid Gated-DeltaNet (30) + full attention (10),
MTP-1, vocab 248,320, native context 262,144.

## License
Apache-2.0. See `NOTICE.md`. ROX N branding applies to this build and the
software; base-model copyright remains Qwen/Alibaba, retained per license.

## Intended use
Local, private agent: chat, tool use, chip/Verilog engineering (ROX N
Silicon Lab), autonomous learning. Not a certified safety-critical system.
