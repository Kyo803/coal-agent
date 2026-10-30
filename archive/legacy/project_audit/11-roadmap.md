# 11 — Roadmap, Known Gaps, Recommendations

This is the forward-looking audit. It consolidates the saved
`BACKLOG.md` plus everything learned while building.

## Immediate / high value

### A. Image editing (`edit_image`) — **DONE (2026-09-30)**
FLUX.2 klein 4B natively supports editing an existing image:
- `-r <ref>` reference edit (PROVEN: fox → watercolor)
- `-i <init>` init-image restyle with `--strength`
Wired as a live `edit_image` tool: parks the 35B, runs
`resources.swap_for_edit`, saves `edited_...png` into the project
`images\`, journals it. Intent rules ("edit/change/turn/recolor my
image into..."). Verified live (portrait → cyberpunk).

### B. Web search without `ddgs` — **DONE (2026-09-30)**
`web_search` now uses a pure-`urllib` **Bing** fallback (DuckDuckGo HTML
blocks bots). No install needed. Verified live.

### C. Image understanding input
Support `python coal.py --ask-image path.png "question"` and dropped
paths so "what's in this image" is easy to use (currently needs a path
in the message).

## Medium

### D. Web API / frontend layer (deferred by user)
`flask`, `fastapi`, `uvicorn` are already installed. Plan:
- `web_api.py` FastAPI on port 8090
- `/api/chat` SSE streaming (tokens + thinking)
- `/api/status`, `/api/sessions`
- `/api/generate_image` (async job + `/api/jobs/<id>`)
- `/api/ask_image`, `/api/tools`, `/api/project`
- `/api/images/<file>` static
- CORS enabled; optionally serve a built-in HTML chat page at `/`

The user will build a proper frontend slowly; Coal just needs the API.

### E. Auto-tier image models (RAM-aware)
Currently one model (FLUX.2 klein 4B). If a swap frees >16 GB, could
auto-select a bigger model (FLUX.2 klein 9B or Qwen Image) — but both
are slower on the RX 570 and 9B is non-commercial. Low priority.

## Known gaps / honest limitations

1. **Text rendering in images** — FLUX.2 klein misspells text (menus,
   logos, infographics). For "logo with words", Coal's 35B can
   hand-write SVG/HTML instead — a cleaner path.
2. **Image gen speed** — 2.5-4 min @ 1024 on the RX 570. A newer GPU or
   `--hires` upscaling would help; `--hires` is slow on this card.
3. **RAM ceiling** — 24 GB total, 35B working set ~10-15 GB under load.
   Embeddings fall back to TF-IDF when Ollama is squeezed (still 100%
   on memory tests). The swap pauses chat during image gen.
4. **Single-conversation** — one `Coal` instance = one conversation at a
   time. Fine for a personal assistant; a web API would let a frontend
   multiplex sessions.
5. **Model identity** — the 35B says "I am Qwen" (weights); file/code/
   config/doc traces are all rebranded Coal. Re-serializing the GGUF
   metadata would fully hide it but risks the 19.7 GB file.
6. **Training track** — 500M/1B checkpoints are research artifacts, not
   production. Documented in `08-training-track.md`.
7. **`LOCAL_RUN.md`** — slightly stale (mentions CPU-only + older
   paths); `OVERVIEW.md` and this audit are authoritative.

## Recommendations for a company handover

1. **Freeze the runtime as the shipped product.** It is proven
   end-to-end (chat, memory, tools, projects, images).
2. **Add the web API (D)** so a frontend can be built against a stable
   contract — the highest-leverage next investment.
3. **Add `edit_image` (A)** — it's the one capability that's fully
   proven at the tool level but not wired into chat.
4. **Add CI**: a GitHub Action (or local script) running
   `test_tools.py` + `eval/suite.py --scale quick` on every change.
5. **Add a `--safe-workspace` mode** for untrusted prompt scenarios
   (confine all file tools to a sandbox dir).
6. **Document secrets hygiene**: never put API keys / the `.lmstudio`
   source path in the repo; `install.py` search paths are already
   neutralized.
7. **Benchmark on target hardware** before scaling (the numbers here are
   for this specific 24 GB / RX 570 box).

## Git/repo hygiene notes

- `~/.coal` is runtime data — never commit.
- `ckpt_*.pt` (2.8 GB each), `*.gguf`, image `out\` are not source.
- Large generated datasets (`data_fresh/`, `bigindex/`, `*.jsonl`)
  should not be in version control.
- The `hub/models/.../model.yaml` documents the 35B provenance.

## Final word

Coal is a complete, local, working personal AI: a real 35B brain with
forever memory, 356 permission-gated tools, project awareness, vision,
and image generation — all offline, all on one 24 GB machine, with a
defense-in-depth security model. The audit folder documents every file,
every subsystem, every decision, and every known gap so a new team can
maintain and extend it with full context.