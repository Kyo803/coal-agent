# Coal — 3D, Tiled Texturing, Image→3D, GPU Compute & Toolchains

_Updated 2026-10-14. New PC (`gamel`), AMD Radeon RX 570 8 GB._

## 0. Can we build "CUDA for the RX 570"?

**No — and you don't need to.** CUDA is NVIDIA-proprietary. AMD's equivalent
is ROCm, and **ROCm dropped Polaris (RX 570 = `gfx803`)** years ago, so
modern PyTorch-ROCm won't run on it (and ROCm barely exists on Windows).

On Windows, *any* DirectX-12 GPU — Polaris included — can do GPU compute
through **DirectML**. That is the practical "CUDA-for-AMD-on-Windows".

So Coal ships **`Coal-Compute`**: not a new compiler/driver stack (that *is*
ROCm — a multi-year effort), but a thin accelerator layer that detects and
drives whatever exists:

```
directml  →  cuda  →  cpu
```

### Measured on this machine (RX 570, DirectML vs CPU)
| workload | DirectML | CPU | speed-up |
|---|---|---|---|
| conv stack 256² | 4.17 ms/iter | 12.90 ms/iter | **3.09×** |
| conv stack 512² | 15.22 ms/iter | 63.14 ms/iter | **4.15×** |

Polaris has **no tensor cores and no fast FP16**, so ~5 TFLOPS FP32 is the
ceiling. Consequence: AI should make a **few razor-sharp seed tiles**, and
the tiler fills the rest — not generate every tile with AI.

### The ML runtime lives apart
Coal runs on Python 3.15, which has no ML wheels yet. So the accelerator
worker runs in a dedicated **Python 3.12 venv** (`~/.coal/ml/venv312`) with
`onnxruntime-directml`. Coal talks to it over a tiny JSON pipe
(`compute.run()`), keeping the main interpreter clean and portable.

## 1. Tiled texturing (your idea, implemented)

```
mesh → xatlas UV unwrap → tile plan (512/1024/2048)
     → per-tile synthesis → feathered seamless stitch
     → bakes: curvature, AO, normal, roughness, ORM
     → apply + export: glb · obj+mtl · fbx · usdz
```

Every tile samples the **same global coordinates**, so overlaps agree
exactly and blending removes seams (verified: mean pixel diff **1.44/255**).
Resolution is limited only by RAM/disk. Stitching is **banded**, so 8K/16K
never blow memory.

### Backends
| backend | what | deps |
|---|---|---|
| `procedural` | fBm + ridged noise + grain, seamless by construction | numpy |
| `grounded` | sample a reference image across the atlas | numpy |
| `ai` | **AI seed tiles + image-quilting** (below) | DirectML + model |

### AI texturing = seeds + quilting
Because a full AI pass over hundreds of tiles is hours on Polaris, Coal:
1. generates **1–4 high-quality seed tiles** with a Turbo diffusion model on
   the GPU (~4 steps each);
2. **quilts** them into the full atlas — each output patch is the
   best-matching random crop (SSD over the overlap with placed neighbours),
   then feathered in. Non-repeating, seam-light, from a handful of AI tiles;
3. adds procedural detail + unsharp on top.

### Model ladder (never fails)
```
dreamshaper8-ort  →  sdxl-turbo-ort  →  sd-turbo-ort  →  procedural
```
`-ort` models are **plain-ops ONNX exports** (via `optimum`) that DirectML
runs. The `onnxruntime/*` demo models are CUDA-only (they contain
`com.microsoft.SkipGroupNorm` / `NhwcConv`, which the DML EP does not
implement) — see `compute/export_onnx.py`.

**Which model, and why (important):**
| model | use for | notes |
|---|---|---|
| **dreamshaper8-ort** | **game/concept art, characters** | SD1.5 stylized checkpoint; supports **CFG + negative prompts**; ~2 GB; 25 steps; painterly and sharp |
| sd-turbo-ort | fast texture seeds | SD2.1 distilled; 4 steps; **no CFG**; photoreal-leaning and soft — wrong tool for stylized art |
| sdxl-turbo-ort | — | not exported (9.7 GB, borderline on 8 GB VRAM) |

The lesson: for stylized characters the **checkpoint** decides the look, and
**CFG + negative prompts** (which only non-Turbo models support) are what
stop "photorealistic and blurry". SD-Turbo at guidance 0 drifts badly.

Any SD checkpoint can be used: `export_onnx.py <hf-repo> <name>`, and if it
ships a non-Euler scheduler (PNDM/DDIM/DEIS) `sd.py` substitutes an Euler
config with the same betas/spacing. **Single-file community checkpoints**
(`.safetensors`/`.ckpt`, the usual form for SD1.5 fine-tunes) are converted
to diffusers format automatically before export.

**Status: `sd-turbo-ort` and `dreamshaper8-ort` both work on DirectML.**
Measured (RX 570): SD-Turbo UNet step 6.3 s / VAE 2.4 s (GPU) vs 11.1 s
(CPU); DreamShaper 512² 25-step CFG image in ~35 s.

Export gotchas solved along the way (all handled in `export_onnx.py`):
`transformers<5` for optimum, `onnxscript`, a UTF-8 stdout (torch prints
emoji), an `os.remove` guard (optimum deletes optional external-data files),
and **torch 2.5.1** (2.14's dynamo exporter fails on the UNet's dynamic axes).

**Pipeline correctness (verified bit-for-bit against diffusers):** the ONNX
UNet and text encoder now match PyTorch to `0.000000`. Three bugs were found
and fixed by comparing against the reference:
1. Euler step sign was flipped (`s0 - s1` instead of `s1 - s0`) — it *added*
   noise. Result was pure static.
2. **`scale_model_input`**: Euler needs the UNet input divided by
   `sqrt(sigma^2 + 1)`; feeding the raw latent produced abstract blobs.
3. CLIP pads with its **pad token** (`"!"` → id 0), not `eos` — wrong padding
   shifted every padded position and wrecked the conditioning.

Verification method that caught all three: run the reference PyTorch pipeline
and diff the **latents step by step**, plus compare the ONNX UNet's `eps`
against PyTorch for identical inputs.

**8 GB DirectML rules (learned the hard way — each violation is a native
access violation, not a Python error):**
1. **One accelerator session at a time.** Creating a text-encoder session
   while the UNet session is open crashes. So all embeddings are computed
   *before* the UNet is created.
2. **No batch-2 CFG.** Classifier-free guidance is done as two sequential
   batch-1 passes; the doubled activation batch tips the driver over.
3. **The VAE encoder runs on CPU** (small, once per tile) so the UNet gets
   the whole card.
4. Sessions are freed with `gc.collect()` between phases.

## 1b. High-resolution images (MultiDiffusion)

For *pictures* (concept art, character sheets) the same "divide and
combine" idea is applied with **MultiDiffusion**:

```
one shared latent  →  at every step, run the UNet per tile
                   →  each tile may carry its OWN region prompt
                   →  blend the overlapping noise predictions
                   →  decode once  →  one coherent high-res image
```

This is the difference between "a big blurry image" and "each region
finished in detail, then combined". `generate_hd_image` exposes it
(`size`, `tile`, `stride`, `tile_prompts`). At 1024² with 512 px tiles and
256 px stride that is a 3×3 grid — nine detailed regions blended into one
picture.

**Important:** use **one shared prompt** for a coherent subject. Because the
tiles share a single latent, a shared prompt yields one consistent image;
divergent *per-tile* prompts average incompatible noise predictions and
produce a **collage**. Per-tile prompts are only useful for broad region
splits (sky vs ground), not for describing different subjects.

## 2. PBR + high resolution (Step 2)
- **Banded stitching** → 4K/8K/16K without exhausting RAM.
- **Normal maps**: geometry normal (curvature → normal) **combined with**
  `normal_from_albedo` (high-pass → Sobel → tangent-space normal).
- **ORM pack**: one map, R=AO, G=roughness, B=metallic (metallic from style).
- **glTF material** now carries `baseColorTexture` **+ `normalTexture` +
  `metallicRoughnessTexture` + `occlusionTexture`** (previously baseColor only).
- Optional **mipmap chain**.

Measured: 4K with full PBR in ~96 s; 8K (8192², 81 tiles) in ~383 s.

## 3. Image → 3D
`relief` · `silhouette` · `depth` (AI-depth slot). Photo becomes the texture.

## 4. Tools (category `3d`)
`generate_3d · render_3d · list_3d_shapes · convert_3d · validate_3d ·
repair_3d · texture_3d · image_to_3d · list_3d_backends`

Primitives include **`man`** (low-poly humanoid, aliases `human`/`person`/
`humanoid`/`figure`). Texture styles include **`spiderman`/`web`** (procedural
red webbed base + dark web lines + blue panels, seamless across tiles).

Worked example produced by Coal:
```
generate a low poly man with a spiderman texture in glb and fbx
→ low_poly_man: 190 verts / 210 faces
→ 2048² texture, 25 tiles, PBR (albedo/normal/roughness/AO/ORM/mipmaps)
→ spiderman_man.glb (embedded) · .fbx · .obj+mtl
```

Plain language works:
```
generate a low poly rocket 3d model in fbx and obj
texture this model <path>.obj with a hull style in glb and fbx
paint this model <path>.obj with ai, photorealistic rivets
turn this image into 3d from <path>.png
```

## 5. Toolchains
| tool | status | where |
|---|---|---|
| iverilog 13 / vvp / gtkwave | ✅ native (no admin) | `C:\msys64\ucrt64\bin` |
| Blender 5.2.2 | ✅ | `C:\Program Files\Blender Foundation\Blender 5.2` |
| Python 3.12 + onnxruntime-directml | ✅ | `~/.coal/ml/venv312` |
| **WSL** | ⛔ needs an admin prompt | run `setup_wsl.ps1` |

`toolchain.py` fixes PATH at startup (MSYS2 binaries need their own bin dir
for their DLLs). `verify_toolchain.py` reports host + WSL + accelerator.

### WSL (one click, needs UAC)
```powershell
powershell -ExecutionPolicy Bypass -File setup_wsl.ps1
```
Self-elevates, enables the features, installs WSL, re-attaches your surviving
sandbox disk (`D:\Coal_SANDBOX\Ubuntu-24.04\ext4.vhdx`), then installs
`iverilog verilator gtkwave` inside it. WSL is for Verilog/tooling — **no GPU
acceleration for Polaris there**.
