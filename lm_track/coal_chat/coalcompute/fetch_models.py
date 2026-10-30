"""Download the ONNX diffusion models Coal uses for AI texturing.

SD-Turbo is the safe primary (2.6 GB, fits 8 GB VRAM easily).
SDXL-Turbo is the top rung (9.7 GB, borderline on 8 GB) — attempted after.
"""
import os
import sys

from huggingface_hub import snapshot_download

ROOT = os.path.join(os.path.expanduser("~"), ".coal", "ml", "models")
SKIP = ["*.ckpt", "*.safetensors", "*safety_checker*", "*vae_encoder*",
        "*.bin", "*.msgpack", "*.h5"]


def get(repo, dest):
    print(f"=== downloading {repo} -> {dest}", flush=True)
    try:
        p = snapshot_download(repo_id=repo, local_dir=dest,
                              allow_patterns=None, ignore_patterns=SKIP,
                              max_workers=4)
        print("OK", repo, p, flush=True)
        return True
    except Exception as e:
        print("FAIL", repo, str(e)[:300], flush=True)
        return False


if __name__ == "__main__":
    jobs = [("onnxruntime/sd-turbo", "sd-turbo")]
    if "--all" in sys.argv:
        jobs.append(("onnxruntime/sdxl-turbo", "sdxl-turbo"))
    for repo, name in jobs:
        get(repo, os.path.join(ROOT, name))
    print("done", flush=True)
