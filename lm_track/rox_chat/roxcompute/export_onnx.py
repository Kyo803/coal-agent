"""Export a diffusers model to a DirectML-friendly ONNX pipeline.

The onnxruntime/* demo models are CUDA-optimised (they contain
com.microsoft.SkipGroupNorm / NhwcConv, which the DirectML EP does not
implement). Exporting ourselves via optimum produces plain Conv/GroupNorm/
Attention ops that DirectML runs natively.

    python export_onnx.py stabilityai/sd-turbo sd-turbo-ort
    python export_onnx.py stabilityai/sdxl-turbo sdxl-turbo-ort
"""
import os
import sys
import time

# torch.onnx prints emoji to stdout; a cp1252 Windows console crashes on it.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# optimum's exporter calls os.remove() on optional external-data files that
# may not exist (small tensors stay inline) -> FileNotFoundError. Make the
# removal tolerant for the duration of the export.
_real_remove = os.remove


def _safe_remove(path, *a, **k):
    try:
        _real_remove(path, *a, **k)
    except FileNotFoundError:
        pass
    except IsADirectoryError:
        pass


os.remove = _safe_remove

MODEL = sys.argv[1] if len(sys.argv) > 1 else "stabilityai/sd-turbo"
NAME = sys.argv[2] if len(sys.argv) > 2 else "sd-turbo-ort"
OUT = os.path.join(os.path.expanduser("~"), ".rox", "ml", "models", NAME)
os.makedirs(OUT, exist_ok=True)

def _diffusers_dir(model):
    """Return a local diffusers-format directory for `model`.

    Handles both diffusers repos and single-file checkpoints (.safetensors /
    .ckpt), which are the common form for community SD1.5 fine-tunes: those
    get converted to a local diffusers folder first."""
    from huggingface_hub import HfApi, hf_hub_download
    try:
        hf_hub_download(model, "model_index.json")
        return model
    except Exception:
        pass
    print("no model_index.json -> treating as a single-file checkpoint",
          flush=True)
    info = HfApi().model_info(model, files_metadata=True)
    cands = [(s.rfilename, s.size or 0) for s in info.siblings
             if s.rfilename.endswith((".safetensors", ".ckpt"))]
    if not cands:
        raise RuntimeError(f"no checkpoint file found in {model}")
    fn, _sz = max(cands, key=lambda x: x[1])
    print("downloading", fn, flush=True)
    path = hf_hub_download(model, fn)
    local = os.path.join(os.path.expanduser("~"), ".rox", "ml", "models",
                         "_src_" + model.replace("/", "_"))
    if os.path.exists(os.path.join(local, "model_index.json")):
        return local
    from diffusers.pipelines.stable_diffusion.convert_from_ckpt import (
        download_from_original_stable_diffusion_ckpt)
    print("converting to diffusers format ->", local, flush=True)
    pipe = download_from_original_stable_diffusion_ckpt(
        checkpoint_path_or_dict=path,
        from_safetensors=fn.endswith(".safetensors"),
        load_safety_checker=False)
    pipe.save_pretrained(local)
    return local


t0 = time.time()
print(f"exporting {MODEL} -> {OUT}", flush=True)
try:
    if "xl" in MODEL.lower():
        from optimum.onnxruntime import ORTStableDiffusionXLPipeline as P
    else:
        from optimum.onnxruntime import ORTStableDiffusionPipeline as P
    src = _diffusers_dir(MODEL)
    pipe = P.from_pretrained(src, export=True)
    pipe.save_pretrained(OUT)
    print(f"OK exported in {time.time()-t0:.0f}s", flush=True)
except Exception as e:
    print("FAIL", repr(e)[:400], flush=True)
    raise
