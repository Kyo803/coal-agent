# 06 — Vision & Image Generation

Coal does **both** halves of visual AI locally: it *understands* images
and it *generates* images.

## Image understanding (no swap needed)

`vision.py` sends images to the 35B's mmproj (vision projector) as
OpenAI-style content arrays → the server converts to the model's
`<|vision_start|><|image_pad|><|vision_end|>` format.

- `encode_image(path)` — base64 data URL
- `build_message(images, question)` — OpenAI multimodal content
- `ask_about_image(images, question)` — returns the model's answer
- `ocr_image` tool → routes to the vision model for text extraction

Server must run with `--mmproj` (server_manager does when
`cfg.model.vision = true`).

**Intent routing (added):**
- "what's in this image / describe this photo / look at this picture"
  → `ask_about_image`
- "read the text in this image / OCR this" → `ocr_image`

These run on the **already-running 35B** — no resource swap needed.

## Image generation (with resource swap)

**Model**: FLUX.2 klein 4B (Q8_0, ~4 GB) — the best/fastest model for
the RX 570. Apache-2.0, step-distilled (4 steps, cfg 1.0).

**Backend**: `stable-diffusion.cpp` (`sd-cli.exe`, win-vulkan build)
at `Coal\image\`, models at `Coal\image\models\`:
- `flux-2-klein-4b-Q8_0.gguf` (4 GB)
- `Qwen3-4B-Q4_K_M.gguf` (text encoder, 2.4 GB)
- `flux2_vae.safetensors` (VAE, 160 MB)

**Why the swap?** The 35B (19.7 GB) and FLUX (4 GB + buffers) can't share
24 GB RAM + 8 GB VRAM. `resources.py` time-slices them.

### `resources.py` — the resource-swap coordinator

```
swap_for_image(prompt, out_png, sm):
  1. sm.stop()              # park the 35B (frees ~10-15GB RAM + 8GB VRAM)
  2. wait free RAM >= 6 GB
  3. sd-cli generate        # Vulkan + CPU offload
  4. sm.ensure()            # reload the 35B
```

`generate_image()` builds the sd-cli command:
```
sd-cli.exe --backend vulkan0
  --diffusion-model flux-2-klein-4b-Q8_0.gguf
  --vae flux2_vae.safetensors
  --llm Qwen3-4B-Q4_K_M.gguf
  -p "<prompt>"
  -n "blurry, pixelated, low quality, ..."   # quality negative prompt
  --cfg-scale 1.0 --steps 4 --sampling-method euler
  -W 1024 -H 1024 --seed -1                   # random seed
  --offload-to-cpu --diffusion-fa
  -o out.png
```

### `tools/handlers_image.py`

- Reads width/height from `config.json → image` (default 1024×1024)
- Saves PNG into the active project's `images\` (else workspace)
- Journals the new image into the project
- Prints "rendering your image... I'll be right back" while parked

### Config (`config.json → image`)

```json
"image": {
  "model": "flux2-klein-4b",
  "backend": "vulkan0",
  "steps": 4,
  "width": 1024,
  "height": 1024,
  "timeout": 900
}
```

## Verified results

| Prompt | Result |
|---|---|
| "a red fox in an autumn forest" | 512×512 PNG in ~48s |
| "a cute robot arm" | full swap: park → generate → reload ✓ |
| "a majestic eagle over mountains at sunset" | **1024×1024, 2.06 MB** |
| "a detailed portrait of a knight in armor" | 1024×1024 (before config fix) |
| **Image editing** (reference): fox → watercolor | `-r` reference edit works ✓ |

## Honest performance

- 512×512: ~48s · **1024×1024: ~2.5-4 min** on the RX 570
- The swap adds ~30-60s to reload the 35B after each image
- 1024 is FLUX.2 klein's **native training resolution** — 512 was blurry
  because it's below native

## Custom images from user specifications (`custom_image`)

`custom_image` parses a natural-language spec (subject, style, mood,
color, aspect ratio) and generates from scratch — or recreates an
existing image to match (pass `recreate` path).

- Styles: cyberpunk, watercolor, oil painting, pixel art, anime,
  cartoon, photorealistic, 3d render, minimalist, vintage, neon, comic,
  sketch, fantasy, steampunk, gothic, isometric, pastel...
- Ratios: square/1:1, 16:9, 9:16, 4:3, 3:4, landscape, portrait
- Colors + moods supported
- Verified live: "a dragon in cyberpunk style, red, 16:9" → **1280×720**
  (16:9) cyberpunk dragon

## Image editing (BUILT — live)

`edit_image` is wired end-to-end. FLUX.2 klein edits via:
- `-r` reference edit (klein-native): "change test_fox.png to a painting"
- `-i` init restyle + `--strength`: "recolor this picture to blue"

It parks the 35B (`resources.swap_for_edit`), saves `edited_...png` into
the project `images\`, and journals it. **Verified live**: a portrait
restyled into a cyberpunk scene (1024×1024, 2.56 MB).