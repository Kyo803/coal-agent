# Coal - Future Changes (saved notes)

Method for future work, captured so it's not lost. Includes the **image
recreation / editing** capability (edit an existing picture into
something else) and other pending ideas.

> **STATUS 2026-09-30 (Part 1 capabilities BUILT)**: Coal can now
> *learn* and *build*:
> - `ingest_docs` / `search_docs` (knowledge category) — learn from a
>   URL, file, folder, or raw text into the RAG index.
> - `langpacks.py` — curated TypeScript/React/Tailwind/Vite/Verilog
>   cheatsheets, auto-installed + ingested; the **write path injects the
>   matching pack** for the file type being written.
> - `setup_toolchain` (build category) — installs a stack's packages via
>   npm / winget / pip.
> - `build_project` — **autonomous multi-file builder**: one prompt ->
>   plan -> write files -> audit -> repair -> verify. Auto-approves its
>   own writes/verify within the build. Verified end-to-end (built a
>   working `cli-calc` project, pytest 5/5).
> - `edit_self` / `backup_self` / `restore_self` / `list_backups` /
>   `restart_self` (self category) — Coal may modify its own core files
>   with backup + syntax validation + restart.
> - Tests: `test_build.py` (38 checks) + tool suite 145/145.

> **STATUS 2026-09-30**: Image editing is now **BUILT and working**
> (`edit_image` tool wired end-to-end). See the section below for the
> live feature, and "OTHER PENDING ITEMS" for what's still open.

---

## IMAGE EDITING / RECREATION (BUILT — done)

**Live feature**: `edit_image` is wired into Coal.
- "edit this image into a watercolor"
- "turn my logo.png into a cartoon"
- "change test_fox.png to a painting"
- "recolor this picture to blue"

It parks the 35B, runs FLUX.2 klein reference/init edit via
`resources.swap_for_edit`, saves `edited_...png` into the project
`images\`, and journals it. Verified live: a portrait was restyled into
a cyberpunk scene (1024×1024).

### The two modes sd-cli offers

| Flag | Meaning | Use case |
|---|---|---|
| `-i, --init-img <path>` | Initial image; denoising starts from it (strength-controlled) | img2img / restyle / repaint |
| `-r, --ref-image <path>` | Reference image the model reads and transfers content from | FLUX Kontext-style edits (klein supports this) |
| `--img-cfg-scale <float>` | Image guidance strength | how strongly to follow the reference |
| `--strength <float>` | Amount of noise to add (0-1) for `-i` mode | 0.75 default |

### Verified working recipe (from sd.cpp docs + discussions)

**PROVEN 2026-09-30**: edited `test_fox.png` -> watercolor painting via
`-r` (reference image). Output on Desktop as `test_fox_watercolor.png`.
Takeaway: the `-r` edit path works; wiring `edit_image` into Coal is
ready to build.

```
sd-cli.exe --diffusion-model flux-2-klein-4b-Q8_0.gguf \
           --vae flux2_vae.safetensors \
           --llm Qwen3-4B-Q4_K_M.gguf \
           -r kontext_input.png \
           -p "change 'flux.cpp' to 'klein.cpp'" \
           --cfg-scale 1.0 --sampling-method euler \
           --diffusion-fa --offload-to-cpu --steps 4 \
           -o edited.png
```

- klein is step-distilled: keep `--steps 4`, `--cfg-scale 1.0`
- `-r` = edit-with-reference; `-i` = init-image restyle
- `--strength` only works with `-i` (not `-r`); if you lower strength
  with `-i`, raise steps (e.g. 0.5 strength -> 6 steps)

### How to wire it into Coal (future build plan)

1. New tool `edit_image` in `tools/handlers_image.py`:
   - args: `path` (source image), `prompt` (what to change it into),
     `strength`/`img_cfg_scale` optional
   - reuses `resources.py` swap (park 35B -> run sd-cli -> reload)
   - writes `edited_<stem>_<ts>.png` next to the source / in project
   - journal it like `generate_image`
2. Intent rule: `edit / change / turn / convert <my image> into <...>`,
   `recolor this`, `restyle this picture as <style>` -> `edit_image`
3. Config `image.edit` defaults (strength, img_cfg_scale)
4. Test: take `test_fox.png` -> "make it a watercolor painting" ->
   verify new PNG

### Files to change (future)
- `tools/handlers_image.py` (add `edit_image`)
- `tools/specs.py` (register `edit_image`)
- `tools/intent.py` (edit rules)
- `tools/exec.py` `_NATIVE_SCHEMAS` (if native)
- `config.json` `image.*`
- `resources.py` (add `edit_image` runner with -r / -i)
- `test_tools.py` (intent + model-path tests)

---

## OTHER PENDING ITEMS (captured for future)

### 1. Web search without `ddgs` — DONE
`web_search` now has a pure-`urllib` **Bing** fallback (DuckDuckGo HTML
blocks bots). Works with no install. Verified live.

### 2. Image understanding input (dropped file / --ask-image)
Currently "what is in this image" needs a path in the message. Add:
`python coal.py --ask-image path.png "question"` and support pasted
paths / dropped files in the chat loop.

### 3. Frontend / web API (deferred, per user)
- `web_api.py` (FastAPI, port 8090): `/api/chat` SSE stream,
  `/api/status`, `/api/generate_image` (async job), `/api/ask_image`,
  `/api/tools`, `/api/project`, `/api/images/<file>`
- flask/fastapi/uvicorn already installed.
- User will build a proper frontend slowly; Coal just needs the API.

### 4. Better image model (only when RAM allows)
- FLUX.2 klein 9B (~29GB bf16, non-commercial) - better but needs
  more RAM than this 24GB box can spare alongside the 35B.
- Qwen Image 20B - best text rendering, but slow on RX 570.
- Current: FLUX.2 klein 4B Q8_0 1024x1024 (chosen: speed + quality).

### 5. Faster image gen
- RX 570 Vulkan ~48s @ 512, ~2.5-4min @ 1024. An upgrade to a newer
  GPU (or `--hires` upscale) would speed it up. `--hires` exists but is
  slow on this card - not recommended.

---

## CURRENT STATE (as of last verified run)

- Terminal chat: intact, streams, recalls memory ("WERU").
- Image generation: FLUX.2 klein 4B Q8_0, 1024x1024, negative prompt,
  random seed, resource-swap (park 35B / generate / reload).
- **Image editing: built + verified** (`edit_image`, ref + init modes).
- **Web search: pure-urllib Bing fallback (no ddgs needed).**
- 356+ tools (now 357 with edit_image), 14 categories + project
  awareness + journaling.
- Tool suite 126/126, full regression 15/15.
- Generated images: `~/.coal/work/images\` or `<project>\images\`.