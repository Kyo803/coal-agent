"""3D model generation tool handlers.

Generate procedural/parametric 3D models (OBJ/STL/glTF + PNG preview),
optionally from a text description (the local model turns the description
into a primitive graph). Render previews of existing meshes.
"""
from __future__ import annotations

import json
import os

import threed
from .handlers_fs import _resolve

NUM_KEYS = ("r", "R", "h", "seg", "rings", "tube", "scale", "height",
            "size", "sx", "sy", "sz", "base", "width", "resolution")


def _fmts(v):
    if not v:
        return None
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return list(v)


def _ask(prompt):
    """Best-effort LLM call to the local server (returns '' if down)."""
    import urllib.request
    from coal_config import cfg
    try:
        body = {"model": "local",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 600, "temperature": 0.3, "stream": False,
                "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request(
            cfg.base_url + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read().decode())
        return d["choices"][0]["message"]["content"]
    except Exception:
        return ""


def _outdir(args, ctx):
    if args.get("outdir"):
        return _resolve(args["outdir"], ctx)
    return os.path.join(os.path.expanduser("~/.coal/work"), "3d")


def generate_3d(args, ctx):
    outdir = _outdir(args, ctx)
    params = {}
    for k in NUM_KEYS:
        if args.get(k) is not None and k != "size":
            params[k] = args[k]
        elif k == "size" and args.get(k) is not None:
            params["size"] = args[k]
    try:
        res = threed.generate(
            outdir,
            shape=args.get("shape"),
            description=args.get("description", "") or "",
            name=args.get("name"),
            size=args.get("size"),
            ask=_ask,
            formats=_fmts(args.get("formats")),
            **{k: v for k, v in params.items() if k != "size"})
    except Exception as e:
        return {"ok": False, "output": f"3d generation failed: {e}"}
    st = res["stats"]
    files = res["files"]
    lines = [f"3D model: {st['name']}  ({st['vertices']} verts, "
             f"{st['faces']} faces, size {st['size']})"]
    for k, v in files.items():
        lines.append(f"  {k:5s}: {v}")
    if res.get("spec"):
        lines.append("  spec: " + json.dumps(res["spec"])[:300])
    return {"ok": True, "output": "\n".join(lines)}


def render_3d(args, ctx):
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    src = _resolve(path, ctx)
    if not os.path.exists(src):
        return {"ok": False, "output": f"not found: {src}"}
    try:
        if src.lower().endswith(".obj"):
            mesh = threed.load_obj(src)
        else:
            return {"ok": False, "output": "only .obj re-render supported"}
        out = args.get("out") or (os.path.splitext(src)[0] + "-preview.png")
        out = _resolve(out, ctx)
        threed.render_png(mesh, out, w=int(args.get("width") or 640),
                          h=int(args.get("height") or 480))
        return {"ok": True, "output": f"rendered {mesh.name} -> {out}"}
    except Exception as e:
        return {"ok": False, "output": f"render failed: {e}"}


def list_3d_shapes(args, ctx):
    return {"ok": True, "output": "shapes: " + ", ".join(
        sorted(threed.SHAPES)) +
        "  (or give a description; examples: tree, rocket, robot, house, "
        "table)"}


def convert_3d(args, ctx):
    """Convert a mesh file to other formats (obj/stl/glb/gltf/ply/off/3mf/
    dae/...). FBX/USDZ need Blender installed."""
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    src = _resolve(path, ctx)
    if not os.path.exists(src):
        return {"ok": False, "output": f"not found: {src}"}
    formats = _fmts(args.get("formats")) or ["obj", "stl", "glb", "ply"]
    base = os.path.splitext(src)[0] + "-conv"
    try:
        m = threed.load_mesh_any(src)
        verts = [tuple(v) for v in m.vertices.tolist()]
        faces = [tuple(int(i) for i in f) for f in m.faces.tolist()]
        mesh = threed.Mesh(verts, faces,
                           os.path.splitext(os.path.basename(src))[0])
    except Exception as e:
        return {"ok": False, "output": f"load failed: {e}"}
    outs = threed.export_mesh(mesh, base, [f.lstrip(".") for f in formats])
    lines = [f"converted {os.path.basename(src)}:"] + \
            [f"  {k}: {v}" for k, v in outs.items()]
    return {"ok": True, "output": "\n".join(lines)}


def validate_3d(args, ctx):
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    src = _resolve(path, ctx)
    if not os.path.exists(src):
        return {"ok": False, "output": f"not found: {src}"}
    try:
        v = threed.validate(src)
    except Exception as e:
        return {"ok": False, "output": f"validate failed: {e}"}
    return {"ok": True, "output": json.dumps(v, indent=1)}


def repair_3d(args, ctx):
    """Repair a mesh (merge verts, fix winding, fill holes) and re-export."""
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    src = _resolve(path, ctx)
    if not os.path.exists(src):
        return {"ok": False, "output": f"not found: {src}"}
    formats = _fmts(args.get("formats")) or ["obj", "stl", "glb"]
    try:
        m = threed.load_mesh_any(src)
        verts = [tuple(v) for v in m.vertices.tolist()]
        faces = [tuple(int(i) for i in f) for f in m.faces.tolist()]
        before = threed.validate(threed.Mesh(verts, faces, "in"))
        fixed = threed.repair(threed.Mesh(verts, faces, "in"))
        after = threed.validate(fixed)
        base = os.path.splitext(src)[0] + "-repaired"
        outs = threed.export_mesh(fixed, base, [f.lstrip(".") for f in formats])
    except Exception as e:
        return {"ok": False, "output": f"repair failed: {e}"}
    lines = [f"repaired {os.path.basename(src)}:",
             f"  before: {before['vertices']}v/{before['faces']}f "
             f"watertight={before['watertight']}",
             f"  after : {after['vertices']}v/{after['faces']}f "
             f"watertight={after['watertight']}"] + \
            [f"  {k}: {v}" for k, v in outs.items()]
    return {"ok": True, "output": "\n".join(lines)}


def _load_mesh(path):
    """Load any supported mesh file into a threed.Mesh."""
    import trimesh
    m = threed.load_mesh_any(path)
    verts = [tuple(v) for v in m.vertices.tolist()]
    faces = [tuple(int(i) for i in f) for f in m.faces.tolist()]
    return threed.Mesh(verts, faces,
                       os.path.splitext(os.path.basename(path))[0])


def image_to_3d(args, ctx):
    """Turn an image into a 3D model (relief / silhouette / depth)."""
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    src = _resolve(path, ctx)
    if not os.path.exists(src):
        return {"ok": False, "output": f"not found: {src}"}
    try:
        import img3d
    except Exception as e:
        return {"ok": False, "output": f"image3d unavailable: {e}"}
    outdir = _outdir(args, ctx)
    try:
        res = img3d.image_to_3d(
            src, outdir, method=args.get("method") or "relief",
            size=int(args.get("size") or 192),
            depth_scale=float(args.get("depth_scale") or 0.6),
            name=args.get("name"), invert=bool(args.get("invert")))
    except Exception as e:
        return {"ok": False, "output": f"image->3d failed: {e}"}
    st = res["stats"]
    lines = [f"image->3d [{st['method']}]: {st['name']}  "
             f"({st['vertices']} verts, {st['faces']} faces)"] + \
            [f"  {k:8s}: {v}" for k, v in res["files"].items()]
    return {"ok": True, "output": "\n".join(lines)}


def texture_3d(args, ctx):
    """UV-unwrap + tile-synthesize + bake + apply a texture to a model."""
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    src = _resolve(path, ctx)
    if not os.path.exists(src):
        return {"ok": False, "output": f"not found: {src}"}
    try:
        import tex3d
    except Exception as e:
        return {"ok": False, "output": f"tex3d unavailable: {e}"}
    outdir = _outdir(args, ctx)
    try:
        mesh = _load_mesh(src)
    except Exception as e:
        return {"ok": False, "output": f"load failed: {e}"}
    fmts = _fmts(args.get("formats")) or ["glb", "obj", "fbx"]
    opts = dict(resolution=int(args.get("resolution") or 2048),
                tile=int(args.get("tile") or 512),
                overlap=int(args.get("overlap") or 64),
                backend=args.get("backend") or "procedural",
                style=args.get("style") or "default",
                prompt=args.get("prompt") or "",
                maps=args.get("maps", True),
                ao_samples=int(args.get("ao_samples") or 16),
                detail=args.get("detail", True),
                sharpen=float(args.get("sharpen") or 0.8),
                band=int(args.get("band") or 1024),
                detail_normal=args.get("detail_normal", True),
                mipmaps=int(args.get("mipmaps") or 0),
                ai_prompt=args.get("ai_prompt") or (
                    args.get("prompt") if args.get("use_ai") else None),
                ai_model=args.get("ai_model"),
                ai_steps=int(args.get("ai_steps") or 4),
                ai_seeds=int(args.get("ai_seeds") or 3),
                formats=fmts, name=args.get("name"))
    try:
        if args.get("parts"):
            res = tex3d.texture_parts(mesh, outdir, **opts)
            lines = [f"textured {res['parts']} parts:"]
            for r in res["results"]:
                lines.append(f"  {r['stats']['name']}: "
                             f"{r['stats']['tiles']} tiles, "
                             f"{len(r['files'])} files")
            return {"ok": True, "output": "\n".join(lines)}
        res = tex3d.texture_mesh(mesh, outdir, **opts)
    except Exception as e:
        return {"ok": False, "output": f"texturing failed: {e}"}
    st = res["stats"]
    lines = [f"textured {st['name']}: {st['resolution']}px, "
             f"{st['tiles']} tiles of {st['tile']}px, "
             f"backend={st['backend']}, style={st['style']}"]
    if st.get("ai"):
        lines.append(f"  ai: {st['ai']}")
    lines += [f"  {k:10s}: {v}" for k, v in res["files"].items()]
    return {"ok": True, "output": "\n".join(lines)}


def generate_hd_image(args, ctx):
    """High-res image via tiled MultiDiffusion.

    The picture is divided into tiles; each tile is denoised in detail
    (optionally with its own region prompt) and the overlapping predictions
    are blended back into one coherent image."""
    try:
        import coalcompute
    except Exception as e:
        return {"ok": False, "output": f"coalcompute unavailable: {e}"}
    prompt = args.get("prompt") or args.get("description") or ""
    if not prompt:
        return {"ok": False, "output": "prompt required"}
    outdir = _outdir(args, ctx)
    name = args.get("name") or "hd_image"
    out = os.path.join(outdir, f"{name}.png")
    log = os.path.join(outdir, f"{name}-tiles.log")
    tp = args.get("tile_prompts")
    if isinstance(tp, str):
        try:
            tp = json.loads(tp)
        except Exception:
            tp = None
    res = None
    mode = (args.get("mode") or "hd").lower()
    model = args.get("ai_model") or coalcompute.pick_model()
    is_turbo = "turbo" in str(model).lower()
    steps = int(args.get("ai_steps") or (4 if is_turbo else 25))
    up_steps = int(args.get("up_steps") or (3 if is_turbo else 12))
    guidance = args.get("guidance")
    guidance = float(guidance) if guidance is not None else \
        (0.0 if is_turbo else 7.0)
    neg = args.get("negative") or ""
    if mode == "tiled":
        res = coalcompute.sd_generate_tiled(
            prompt, out=out, model=model,
            size=int(args.get("size") or 1024),
            tile=int(args.get("tile") or 512),
            stride=int(args.get("stride") or 256),
            steps=steps, seed=int(args.get("seed") or 0),
            tile_prompts=tp, log=log, negative=neg, guidance=guidance)
    else:
        res = coalcompute.sd_generate_hd(
            prompt, out=out, model=model,
            size=int(args.get("size") or 1024),
            base=int(args.get("base") or 512),
            tile=int(args.get("tile") or 512),
            overlap=int(args.get("overlap") or 128),
            strength=float(args.get("strength") or 0.4),
            steps=steps, up_steps=up_steps,
            seed=int(args.get("seed") or 0), log=log,
            negative=neg, guidance=guidance)
    if not res.get("ok"):
        return {"ok": False, "output": f"hd image failed: {res.get('error')}"}
    return {"ok": True, "output": "\n".join([
        f"hd image [{res.get('model')}] {res.get('size')}: {res.get('path')}",
        f"  mode: {mode}  steps: {steps}  guidance: {guidance}",
        f"  tile log: {log}"])}


def character_sheet(args, ctx):
    """Turn one character image into a labelled turnaround sheet
    (front / side / back) by deriving the other views with img2img."""
    try:
        import coalcompute
    except Exception as e:
        return {"ok": False, "output": f"coalcompute unavailable: {e}"}
    path = args.get("path") or args.get("in")
    if not path:
        return {"ok": False, "output": "path required"}
    src = _resolve(path, ctx)
    if not os.path.exists(src):
        return {"ok": False, "output": f"not found: {src}"}
    outdir = _outdir(args, ctx)
    log = os.path.join(outdir, "character-sheet.log")
    model = args.get("ai_model") or coalcompute.pick_model()
    g = args.get("guidance")
    res = coalcompute.sd_character_sheet(
        src, outdir=outdir, prompt=args.get("prompt") or "", model=model,
        strength=float(args.get("strength") or 0.55),
        steps=int(args.get("steps") or 20), seed=int(args.get("seed") or 0),
        guidance=float(g) if g is not None else 7.0,
        negative=args.get("negative") or "", log=log)
    if not res.get("ok"):
        return {"ok": False,
                "output": f"character sheet failed: {res.get('error')}"}
    lines = [f"character sheet [{res.get('model')}]: {res.get('sheet')}"]
    for k, v in (res.get("files") or {}).items():
        lines.append(f"  {k:8s}: {v}")
    return {"ok": True, "output": "\n".join(lines)}


def list_3d_backends(args, ctx):
    try:
        import img3d
        import tex3d
        info = {"texturing": tex3d.backends_info(),
                "image_to_3d": img3d.backends_info()}
        try:
            import coalcompute
            info["compute"] = {
                "probe": coalcompute.probe(),
                "models_present": coalcompute.models_present(),
                "ladder": coalcompute.MODEL_LADDER,
                "pick_model": coalcompute.pick_model(),
            }
        except Exception as e:
            info["compute"] = {"error": str(e)[:160]}
    except Exception as e:
        info = {"error": str(e)}
    return {"ok": True, "output": json.dumps(info, indent=1)}
