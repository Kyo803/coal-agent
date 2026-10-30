"""Coal-Compute — a thin accelerator layer for Coal.

It is NOT a new CUDA/ROCm (that is a multi-year compiler+driver effort).
It is the small, honest piece that makes Coal *portable across whatever
compute exists on the machine*:

    detect()   probe backends, pick the best for a task
    run()      dispatch a job to the accelerator worker
    benchmark() measure real throughput (DML vs CPU) on THIS GPU
    report()   one-call summary for the UI / diagnostics

Backends, in priority order:
    directml  Microsoft DirectML via onnxruntime-directml  (RX 570 on Windows)
    cuda      onnxruntime-gpu, if an NVIDIA card is present
    cpu       always available

The heavy runtime lives in a dedicated Python 3.12 venv
(C:\\Users\\gamel\\.coal\\ml\\venv312) so Coal's own interpreter stays
clean and ML wheels that don't target 3.15 can still be used.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "worker.py")
VENV = os.path.join(os.path.expanduser("~"), ".coal", "ml", "venv312")
VENV_PY = os.path.join(VENV, "Scripts", "python.exe")
MODELS_DIR = os.path.join(os.path.expanduser("~"), ".coal", "ml", "models")

# Accelerator priority. First available wins for a given task.
PRIORITY = ["directml", "cuda", "cpu"]

# Model ladder: best quality first, guaranteed fallback last.
# dreamshaper8-ort is a stylized SD1.5 checkpoint (CFG + negative prompts,
# painterly game-art look) -> the right default for concept art.
# sd-turbo-ort is fast (4 steps) and handy for quick texture seeds.
MODEL_LADDER = ["dreamshaper8-ort", "sdxl-turbo-ort", "sd-turbo-ort",
                "procedural"]
CANDIDATE_MODELS = ["dreamshaper8-ort", "sdxl-turbo-ort", "sd-turbo-ort",
                    "sdxl-turbo", "sd-turbo"]


def worker_python():
    """The interpreter that runs the accelerator worker (or None)."""
    if os.path.isfile(VENV_PY):
        return VENV_PY
    # fall back to the current interpreter if it happens to have the deps
    return sys.executable


def available():
    return {
        "worker": worker_python(),
        "venv": os.path.isdir(VENV),
        "models_dir": MODELS_DIR,
        "priority": PRIORITY,
    }


def run(payload, timeout=1800):
    """Send one JSON job to the worker; return the parsed reply."""
    py = worker_python()
    if not py:
        return {"ok": False, "error": "no worker interpreter"}
    try:
        p = subprocess.run([py, WORKER], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=timeout,
                           creationflags=0x08000000)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s"}
    out = (p.stdout or "").strip().splitlines()
    for ln in reversed(out):
        ln = ln.strip()
        if ln.startswith("{"):
            try:
                return json.loads(ln)
            except Exception:
                continue
    return {"ok": False, "error": (p.stderr or "no output")[-400:]}


def probe():
    return run({"op": "probe"}, timeout=300)


def benchmark(size=512, iters=20, timeout=600):
    return run({"op": "benchmark", "size": size, "iters": iters},
               timeout=timeout)


def pick(task="image"):
    """Choose the best available backend for a task."""
    info = probe()
    provs = info.get("providers", []) if info.get("ok") else []
    if "DmlExecutionProvider" in provs:
        return "directml"
    if "CUDAExecutionProvider" in provs:
        return "cuda"
    return "cpu"


def sd_generate(prompt, out=None, model="sd-turbo", steps=4, seed=0,
                size=512, accel=None, negative="", guidance=0.0,
                timeout=1800):
    """Text -> image on the accelerator. Returns {ok, path|image_b64}."""
    accel = accel or ("DmlExecutionProvider" if pick() == "directml"
                      else "CPUExecutionProvider")
    return run({"op": "sd_generate", "prompt": prompt, "out": out,
                "model": model, "steps": int(steps), "seed": int(seed),
                "size": int(size), "accel": accel,
                "negative": negative or "", "guidance": float(guidance)},
               timeout=timeout)


def sd_generate_tiled(prompt, out=None, model=None, size=1024, tile=512,
                      stride=256, steps=4, seed=0, tile_prompts=None,
                      log=None, accel=None, negative="", guidance=0.0,
                      timeout=3600):
    """High-res image via MultiDiffusion: per-tile prompts, blended into one
    coherent image. Clear error if no AI model is present."""
    model = model or pick_model()
    if model == "procedural":
        return {"ok": False, "error": "no AI model present"}
    accel = accel or ("DmlExecutionProvider" if pick() == "directml"
                      else "CPUExecutionProvider")
    return run({"op": "sd_generate_tiled", "prompt": prompt, "out": out,
                "model": model, "size": int(size), "tile": int(tile),
                "stride": int(stride), "steps": int(steps),
                "seed": int(seed), "tile_prompts": tile_prompts or {},
                "log": log, "accel": accel, "negative": negative or "",
                "guidance": float(guidance)}, timeout=timeout)


def sd_generate_hd(prompt, out=None, model=None, size=1024, base=512,
                   tile=512, overlap=128, strength=0.4, steps=4, up_steps=3,
                   seed=0, log=None, accel=None, negative="", guidance=0.0,
                   timeout=3600):
    """Coherent high-res image: generate at the model's native size (where
    it is coherent), then finish each tile in detail with img2img and blend.
    This is the workflow that avoids MultiDiffusion's collage effect."""
    model = model or pick_model()
    if model == "procedural":
        return {"ok": False, "error": "no AI model present"}
    accel = accel or ("DmlExecutionProvider" if pick() == "directml"
                      else "CPUExecutionProvider")
    return run({"op": "sd_generate_hd", "prompt": prompt, "out": out,
                "model": model, "size": int(size), "base": int(base),
                "tile": int(tile), "overlap": int(overlap),
                "strength": float(strength), "steps": int(steps),
                "up_steps": int(up_steps), "seed": int(seed), "log": log,
                "accel": accel, "negative": negative or "",
                "guidance": float(guidance)}, timeout=timeout)


def sd_tile_upscale(in_path, out=None, prompt="", model=None, size=None,
                    tile=512, overlap=128, strength=0.4, up_steps=12, seed=0,
                    log=None, accel=None, negative="", guidance=7.0,
                    timeout=3600):
    """Finish an existing image at higher resolution: each tile is redone
    with img2img (keeping the composition) and blended."""
    model = model or pick_model()
    if model == "procedural":
        return {"ok": False, "error": "no AI model present"}
    accel = accel or ("DmlExecutionProvider" if pick() == "directml"
                      else "CPUExecutionProvider")
    return run({"op": "sd_tile_upscale", "in": in_path, "out": out,
                "prompt": prompt, "model": model, "size": int(size or 0),
                "tile": int(tile), "overlap": int(overlap),
                "strength": float(strength), "up_steps": int(up_steps),
                "seed": int(seed), "log": log, "accel": accel,
                "negative": negative or "", "guidance": float(guidance)},
               timeout=timeout)


def sd_character_sheet(in_path, out=None, outdir=None, prompt="", model=None,
                       strength=0.55, steps=20, seed=0, guidance=7.0,
                       negative="", order=("front", "side", "back"), log=None,
                       accel=None, timeout=3600):
    """Turn one character image into a labelled turnaround sheet
    (front / side / back) by deriving the other views with img2img."""
    model = model or pick_model()
    if model == "procedural":
        return {"ok": False, "error": "no AI model present"}
    accel = accel or ("DmlExecutionProvider" if pick() == "directml"
                      else "CPUExecutionProvider")
    return run({"op": "sd_character_sheet", "in": in_path, "out": out,
                "outdir": outdir, "prompt": prompt, "model": model,
                "strength": float(strength), "steps": int(steps),
                "seed": int(seed), "guidance": float(guidance),
                "negative": negative or "", "order": list(order),
                "log": log, "accel": accel}, timeout=timeout)


def models_present():
    present = {}
    for name in CANDIDATE_MODELS:
        d = os.path.join(MODELS_DIR, name)
        present[name] = os.path.isfile(os.path.join(d, "unet", "model.onnx"))
    return present


def pick_model(prefer=None):
    """Highest-quality model actually present, else 'procedural'."""
    present = models_present()
    order = MODEL_LADDER if not prefer else [prefer] + [
        m for m in MODEL_LADDER if m != prefer]
    for m in order:
        if m == "procedural":
            return "procedural"
        if present.get(m):
            return m
    return "procedural"


def report():
    info = available()
    info["probe"] = probe()
    return info


if __name__ == "__main__":
    print(json.dumps(report(), indent=1))
