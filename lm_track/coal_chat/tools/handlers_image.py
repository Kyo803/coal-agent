"""Image generation + editing + custom-spec handlers: swap resources
(park the 35B), run stable-diffusion.cpp (FLUX.2 klein 4B) on Vulkan,
save PNGs into the active project (or workspace), and journal them.

  from tools.handlers_image import generate_image, edit_image, custom_image
  res = generate_image({"prompt": "a robot arm"}, ctx)
  res = edit_image({"path": "x.png", "prompt": "make it a watercolor"}, ctx)
  res = custom_image({"description": "a dragon, dark cyberpunk, 16:9"}, ctx)

custom_image parses USER SPECIFICATIONS (subject, style, aspect ratio,
colors, mood) and generates from scratch — or recreates/refines an
existing image to match (pass args.recreate path).
"""
from __future__ import annotations

import os
import re
import time

from coal_config import cfg

# aspect-ratio phrases -> (width, height) at ~1M pixels
RATIOS = {
    "square": (1024, 1024),
    "1:1": (1024, 1024),
    "16:9": (1280, 720),
    "wide": (1280, 720),
    "landscape": (1280, 720),
    "9:16": (720, 1280),
    "portrait": (720, 1280),
    "vertical": (720, 1280),
    "3:2": (1152, 768),
    "2:3": (768, 1152),
    "4:3": (1100, 825),
    "3:4": (825, 1100),
}

STYLES = ["cyberpunk", "watercolor", "oil painting", "pixel art", "anime",
          "cartoon", "photorealistic", "3d render", "minimalist", "vintage",
          "dark", "dreamy", "neon", "comic", "sketch", "fantasy", "steampunk",
          "gothic", "flat design", "isometric", "claymation", "pastel"]

MOODS = ["happy", "sad", "moody", "calm", "dramatic", "mysterious", "bright",
         "gloomy", "epic", "peaceful", "chaotic", "romantic"]

COLORS = ["red", "blue", "green", "purple", "gold", "silver", "black",
          "white", "teal", "pink", "orange", "monochrome", "sepia"]


def _out_dir(ctx):
    """Where generated/edited images go: active project images/, else
    the workspace images/ dir."""
    project = getattr(ctx, "project", None)
    if project is not None:
        out_dir = os.path.join(project.source, "images")
        os.makedirs(out_dir, exist_ok=True)
        return project, out_dir
    out_dir = os.path.join(getattr(ctx, "workspace", "~/.coal/work")
                           or "~/.coal/work", "images")
    os.makedirs(os.path.expanduser(out_dir), exist_ok=True)
    return None, os.path.expanduser(out_dir)


def _journal(project, out_png, action, detail):
    if project is not None:
        try:
            from project.journal import Journal
            rel = os.path.relpath(out_png, project.source).replace("\\", "/")
            j = Journal(project)
            j.record(rel, action, detail)
        except Exception:
            pass


def _dimensions(text, args):
    """Resolve (width, height) from an aspect-ratio phrase in the text or
    explicit width/height args. Defaults to config (1024x1024)."""
    _im = cfg.get("image", {})
    if args.get("width") or args.get("height"):
        return int(args.get("width", _im.get("width", 1024))), \
            int(args.get("height", _im.get("height", 1024)))
    low = (text or "").lower()
    for phrase, wh in RATIOS.items():
        if phrase in low:
            return wh
    return int(_im.get("width", 1024)), int(_im.get("height", 1024))


def parse_specs(text):
    """Extract {subject, style, mood, color, ratio, negative} from a
    natural-language image specification."""
    t = (text or "").strip()
    found_style = next((s for s in STYLES if s in t.lower()), None)
    found_mood = next((m for m in MOODS if m in t.lower()), None)
    found_color = next((c for c in COLORS if c in t.lower()), None)
    ratio = next((r for r in RATIOS if r in t.lower()), None)
    return {
        "subject": t,
        "style": found_style,
        "mood": found_mood,
        "color": found_color,
        "ratio": ratio,
        "negative": (cfg.get("image", {}).get("negative_prompt") or (
            "blurry, pixelated, jpeg artifacts, low quality, deformed, "
            "watermark, text, signature, extra fingers")),
    }


def build_prompt(spec):
    """Turn parsed specs into a rich positive prompt for the model."""
    parts = [spec["subject"]]
    style = spec.get("style")
    mood = spec.get("mood")
    color = spec.get("color")
    if color:
        parts.insert(0, f"{color} color scheme, ")
    if style:
        parts.append(f", {style} style")
    if mood:
        parts.append(f", {mood} mood")
    parts.append(", highly detailed, sharp focus, professional quality")
    return "".join(parts)


def generate_image(args, ctx):
    prompt = args.get("prompt", args.get("text", ""))
    if not prompt:
        return {"ok": False, "output": "prompt required"}
    width, height = _dimensions(prompt, args)
    project, out_dir = _out_dir(ctx)
    stem = "".join(c if c.isalnum() or c in "-_" else "_"
                   for c in prompt[:24].lower()).strip("_") or "image"
    out_png = os.path.join(out_dir, f"{stem}_{int(time.time())}.png")
    if ctx.notify_callback:
        ctx.notify_callback("rendering your image... I'll be right back")
    try:
        from resources import swap_for_image
        from server_manager import ServerManager
        sm = ServerManager()
        ok, msg = swap_for_image(prompt, out_png, sm, width=width,
                                 height=height)
    except Exception as e:
        return {"ok": False, "output": f"image generation failed: {e}"}
    if not ok:
        return {"ok": False, "output": msg}
    _journal(project, out_png, "created", f"generated image: {prompt[:80]}")
    return {"ok": True, "output": f"Image saved: {out_png}"}


def edit_image(args, ctx):
    """Edit an existing image into something else. FLUX.2 klein supports
    reference edits (-r) and init restyles (-i).
      args: path (source), prompt (what to change), mode (ref|init),
            strength (0-1, init mode), width/height"""
    src = args.get("path", args.get("src", ""))
    prompt = args.get("prompt", args.get("text", ""))
    if not src:
        return {"ok": False, "output": "source image path required"}
    if not prompt:
        return {"ok": False, "output": "edit prompt required"}
    src = os.path.abspath(os.path.expanduser(src))
    if not os.path.exists(src):
        return {"ok": False, "output": f"source image not found: {src}"}
    width, height = _dimensions(prompt, args)
    mode = args.get("mode", "ref")  # ref (reference) | init (img2img)
    strength = args.get("strength")
    project, out_dir = _out_dir(ctx)
    base = os.path.splitext(os.path.basename(src))[0]
    stem = "".join(c if c.isalnum() or c in "-_" else "_"
                   for c in prompt[:20].lower()).strip("_") or "edit"
    out_png = os.path.join(out_dir, f"{base}_{stem}_{int(time.time())}.png")
    if ctx.notify_callback:
        ctx.notify_callback("editing your image... I'll be right back")
    try:
        from resources import swap_for_edit
        from server_manager import ServerManager
        sm = ServerManager()
        ok, msg = swap_for_edit(src, prompt, out_png, sm, width=width,
                                height=height, mode=mode, strength=strength)
    except Exception as e:
        return {"ok": False, "output": f"image edit failed: {e}"}
    if not ok:
        return {"ok": False, "output": msg}
    _journal(project, out_png, "created",
             f"edited image ({mode}): {prompt[:80]}")
    return {"ok": True, "output": f"Edited image saved: {out_png}"}


def custom_image(args, ctx):
    """Generate (or recreate/refine) an image to match the USER'S
    SPECIFICATIONS: subject + style + mood + color + aspect ratio.

      args:
        description/text  - natural spec, e.g. "a dragon, cyberpunk,
                            red, moody, 16:9"
        recreate          - optional path to an existing image to
                            recreate/restyle to match the spec
        mode/strength     - for recreate (init/ref)
    """
    desc = args.get("description") or args.get("text") or args.get("prompt")
    if not desc:
        return {"ok": False, "output": "image specification required"}
    spec = parse_specs(desc)
    prompt = build_prompt(spec)
    width, height = RATIOS.get(spec["ratio"], (1024, 1024))
    if args.get("width") or args.get("height"):
        _im = cfg.get("image", {})
        width = int(args.get("width", _im.get("width", 1024)))
        height = int(args.get("height", _im.get("height", 1024)))

    recreate = args.get("recreate", args.get("path"))
    if recreate:
        # recreate / restyle an existing image to match the spec
        return edit_image({
            "path": recreate,
            "prompt": prompt,
            "mode": args.get("mode", "ref"),
            "strength": args.get("strength"),
            "width": width, "height": height}, ctx)

    project, out_dir = _out_dir(ctx)
    stem = "".join(c if c.isalnum() or c in "-_" else "_"
                   for c in desc[:24].lower()).strip("_") or "custom"
    out_png = os.path.join(out_dir, f"{stem}_{int(time.time())}.png")
    if ctx.notify_callback:
        ctx.notify_callback("rendering your custom image... "
                            "I'll be right back")
    try:
        from resources import swap_for_image
        from server_manager import ServerManager
        sm = ServerManager()
        ok, msg = swap_for_image(prompt, out_png, sm, width=width,
                                 height=height)
    except Exception as e:
        return {"ok": False, "output": f"custom image failed: {e}"}
    if not ok:
        return {"ok": False, "output": msg}
    _journal(project, out_png, "created", f"custom image: {desc[:80]}")
    detail = f" [{spec['style']}]" if spec["style"] else ""
    return {"ok": True,
            "output": f"Custom image saved: {out_png}{detail}"}


if __name__ == "__main__":
    from types import SimpleNamespace
    ctx = SimpleNamespace(workspace="~/.coal/work", project=None,
                          notify_callback=lambda m: print("[img]", m))
    for d in ["a dragon, cyberpunk, red, moody, 16:9",
              "a cute robot, watercolor, pastel, square"]:
        s = parse_specs(d)
        print(d)
        print("  ->", {k: v for k, v in s.items() if k != "negative"})
        print("  prompt:", build_prompt(s)[:120])
        print("  size:", RATIOS.get(s["ratio"], (1024, 1024)))