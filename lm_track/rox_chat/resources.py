"""Resource coordinator: time-slices the 35B model and the image
generator so two heavy models never run at once on a tight machine.

  swap_for_image(prompt, out_png, sm)
     1. park the 35B (kill llama-server -> frees ~10-15GB RAM + 8GB VRAM)
     2. wait for RAM to free up
     3. run stable-diffusion.cpp (Vulkan + CPU offload) -> PNG
     4. reload the 35B (sm.ensure) -> reclaims RAM

Everything else (memory, personality, sessions) lives on disk in ~/.rox,
so parking the server loses nothing.
"""
from __future__ import annotations

import os
import subprocess
import time

from rox_config import cfg
from server_manager import free_ram_gb


def image_dir():
    return os.path.join(cfg.install_dir, "image")


def sd_cli_path():
    return os.path.join(image_dir(), "sd-cli.exe")


def models_dir():
    return os.path.join(image_dir(), "models")


def _find_model(prefix, dirs):
    """Find a model file by name prefix in the models dir (or a subdir)."""
    root = models_dir()
    for dp, _, files in os.walk(root):
        for f in files:
            if f.lower().startswith(prefix.lower()):
                return os.path.join(dp, f)
    return None


def model_paths():
    """Return (diffusion, vae, llm) paths from the image config."""
    m = cfg.get("image", {})
    diff = m.get("diffusion") or _find_model("flux-2-klein", models_dir())
    vae = m.get("vae") or _find_model("flux2_vae", models_dir()) \
        or _find_model("diffusion_pytorch_model", models_dir())
    llm = m.get("llm") or _find_model("Qwen3-4B", models_dir())
    return diff, vae, llm


def generate_image(prompt, out_png, width=512, height=512, steps=None,
                   backend="vulkan0", progress_cb=None):
    """Run sd-cli to generate one image. Returns (ok, message)."""
    exe = sd_cli_path()
    if not os.path.exists(exe):
        return False, f"sd-cli missing at {exe}"
    diff, vae, llm = model_paths()
    if not all([diff, vae, llm]):
        return False, f"image models incomplete: diffusion={diff} vae={vae} " \
                      f"llm={llm} (run: download to {models_dir()})"
    m = cfg.get("image", {})
    steps = steps or m.get("steps", 4)
    neg = m.get("negative_prompt") or (
        "blurry, pixelated, jpeg artifacts, compression noise, "
        "oversmoothed, plastic, low quality, deformed, watermark, "
        "low detail")
    args = [exe,
            "--backend", backend,
            "--diffusion-model", diff,
            "--vae", vae,
            "--llm", llm,
            "-p", prompt,
            "-n", neg,
            "--cfg-scale", "1.0",
            "--steps", str(steps),
            "--sampling-method", "euler",
            "-W", str(width), "-H", str(height),
            "--seed", "-1",
            "--offload-to-cpu", "--diffusion-fa",
            "-o", out_png]
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=int(m.get("timeout", 900)),
                           encoding="utf-8", errors="replace",
                           creationflags=0x08000000)
        ok = r.returncode == 0 and os.path.exists(out_png) and \
            os.path.getsize(out_png) > 0
        tail = (r.stdout or "")[-300:] + (r.stderr or "")[-300:]
        if progress_cb:
            progress_cb("generated" if ok else "failed")
        return ok, ("image saved" if ok else f"sd-cli failed:\n{tail}")
    except subprocess.TimeoutExpired:
        return False, f"image generation timed out (>{m.get('timeout',900)}s)"
    except Exception as e:
        return False, f"image generation error: {e}"


def edit_image(src_path, prompt, out_png, width=512, height=512, steps=None,
               mode="ref", strength=None, backend="vulkan0",
               progress_cb=None):
    """Edit an existing image: mode='ref' uses -r (reference edit,
    mode='init' uses -i (img2img restyle, strength-controlled).
    FLUX.2 klein supports both. Returns (ok, message)."""
    exe = sd_cli_path()
    if not os.path.exists(exe):
        return False, f"sd-cli missing at {exe}"
    if not src_path or not os.path.exists(src_path):
        return False, f"source image not found: {src_path}"
    diff, vae, llm = model_paths()
    if not all([diff, vae, llm]):
        return False, f"image models incomplete: diffusion={diff} vae={vae} " \
                      f"llm={llm} (run: download to {models_dir()})"
    m = cfg.get("image", {})
    steps = steps or m.get("steps", 4)
    args = [exe,
            "--backend", backend,
            "--diffusion-model", diff,
            "--vae", vae,
            "--llm", llm,
            "-p", prompt,
            "--cfg-scale", "1.0",
            "--steps", str(steps),
            "--sampling-method", "euler",
            "-W", str(width), "-H", str(height),
            "--seed", "-1",
            "--offload-to-cpu", "--diffusion-fa"]
    if mode == "init":
        args += ["-i", src_path]
        # strength only applies to -i; lower strength needs more steps
        if strength is not None:
            args += ["--strength", str(strength)]
            if float(strength) < 0.7 and args[args.index("--steps") + 1] \
                    == str(m.get("steps", 4)):
                args[args.index("--steps") + 1] = "6"
    else:
        args += ["-r", src_path]  # reference edit (klein-native)
    args += ["-o", out_png]
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=int(m.get("timeout", 900)),
                           encoding="utf-8", errors="replace",
                           creationflags=0x08000000)
        ok = r.returncode == 0 and os.path.exists(out_png) and \
            os.path.getsize(out_png) > 0
        tail = (r.stdout or "")[-300:] + (r.stderr or "")[-300:]
        if progress_cb:
            progress_cb("edited" if ok else "failed")
        return ok, ("image edited" if ok else f"sd-cli failed:\n{tail}")
    except subprocess.TimeoutExpired:
        return False, f"image edit timed out (>{m.get('timeout',900)}s)"
    except Exception as e:
        return False, f"image edit error: {e}"


def swap_for_edit(src_path, prompt, out_png, sm, width=512, height=512,
                  steps=None, mode="ref", strength=None, progress_cb=None,
                  park=True):
    """Swap: park 35B -> edit image -> reload. Returns (ok, msg)."""
    if park:
        if progress_cb:
            progress_cb("parking")
        try:
            sm.stop()
        except Exception:
            pass
        _wait_free_ram()
    ok, msg = edit_image(src_path, prompt, out_png, width=width,
                         height=height, steps=steps, mode=mode,
                         strength=strength, progress_cb=progress_cb)
    if park:
        if progress_cb:
            progress_cb("reloading")
        try:
            sm.ensure()
        except Exception:
            pass
    return ok, msg


def _wait_free_ram(target_gb=6.0, timeout=120):
    """Wait until free RAM >= target (the 35B's mmap working set must
    be released by the OS before the image model loads comfortably)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        f = free_ram_gb()
        if f >= target_gb:
            return True
        time.sleep(2)
    return free_ram_gb() >= 2.0  # give up but allow if some freed


def swap_for_image(prompt, out_png, sm, width=512, height=512, steps=None,
                   progress_cb=None, park=True):
    """Full swap: park 35B -> generate -> reload. Returns (ok, msg)."""
    if park:
        if progress_cb:
            progress_cb("parking")
        try:
            sm.stop()
        except Exception:
            pass
        _wait_free_ram()

    ok, msg = generate_image(prompt, out_png, width=width, height=height,
                             steps=steps, progress_cb=progress_cb)

    if park:
        if progress_cb:
            progress_cb("reloading")
        # always try to bring the 35B back up
        try:
            sm.ensure()
        except Exception:
            pass
    return ok, msg


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    d, v, l = model_paths()
    print("diffusion:", d)
    print("vae:", v)
    print("llm:", l)
    print("ready:", all([d, v, l]))