"""Coal 3D texturing engine — tiles, bakes, UVs, multi-format apply.

Pipeline
    mesh -> xatlas UV unwrap -> tile plan -> per-tile synthesis (backend)
         -> feathered seamless stitch -> geometry bakes (AO / curvature /
            normal / roughness) -> pack PNG maps -> apply (glb/obj/fbx/usdz)

Why tiles: no image model gives an 8K, razor-sharp, perfectly seamless
texture in one shot. Coal instead renders the texture as many independent
tiles (512/1024/2048 px each) that are generated at full detail and then
blended. Detail per tile stays maximal, seams are removed by overlapping
cosine windows, and final size is limited only by RAM/disk.

Backends (pluggable):
    procedural  pure numpy fBm/ridged noise, seamless by construction
    grounded    sample a reference image across the atlas
    ai          call an image generator per tile (local SD / API); the
                callable is passed as ctx["ai"] and falls back to procedural
"""
from __future__ import annotations

import math
import os

import numpy as np

import threed


# ------------------------------------------------------------------ helpers
def _np_mesh(mesh):
    V = np.asarray(mesh.verts, dtype=np.float64)
    try:
        F = np.asarray(mesh.faces, dtype=np.int64)
    except ValueError:                       # mixed quads + triangles
        F = np.array([list(f) for f in mesh.faces], dtype=object)
    return V, F


def _mesh(V, F, name="model"):
    return threed.Mesh([tuple(v) for v in np.asarray(V, float)],
                       [tuple(int(i) for i in f) for f in np.asarray(F, int)],
                       name)


def triangulate(F):
    """Fan-triangulate polygon faces (Coal primitives include quads, and
    composites like the man mix quads and triangles)."""
    out = []
    for f in F:
        f = list(f)
        for i in range(1, len(f) - 1):
            out.append((f[0], f[i], f[i + 1]))
    return np.asarray(out, dtype=np.int64)


def _save_png(arr, path):
    from PIL import Image
    a = np.asarray(arr, dtype=np.uint8)
    Image.fromarray(a).save(path)
    return path


def write_mipmaps(img, base, levels=3):
    """Write a half-resolution mip chain (base-mip1.png ...)."""
    from PIL import Image
    im = Image.fromarray(np.asarray(img, np.uint8))
    w, h = im.size
    outs = []
    for i in range(1, int(levels) + 1):
        w //= 2
        h //= 2
        if w < 8 or h < 8:
            break
        p = f"{base}-mip{i}.png"
        im.resize((w, h), Image.LANCZOS).save(p)
        outs.append(p)
    return outs


def _linspace_img(img, w, h):
    from PIL import Image
    return np.asarray(Image.fromarray(np.asarray(img, np.uint8)).resize(
        (w, h), Image.LANCZOS))


# ------------------------------------------------------------------ unwrap
def unwrap(mesh, res=1024):
    """xatlas UV unwrap. Returns dict with vertices/faces/uvs (numpy)."""
    import xatlas
    V, F = _np_mesh(mesh)
    F = triangulate(F)
    vmapping, indices, uvs = xatlas.parametrize(V.astype(np.float32),
                                               F.astype(np.uint32))
    V2 = V[np.asarray(vmapping)]
    F2 = np.asarray(indices, dtype=np.int64)
    return {"vertices": V2, "faces": F2, "uvs": np.asarray(uvs, float),
            "res": int(res)}


# ------------------------------------------------------------------ noise
def _hash01(ix, iy, seed=0):
    ix = np.asarray(ix, dtype=np.int64)
    iy = np.asarray(iy, dtype=np.int64)
    m = 0xFFFFFFFFFFFF
    h = (ix * 374761393 + iy * 668265263 + np.int64(seed) * 2654435761) & m
    h = (h ^ (h >> 13)) & m
    h = (h * 1274126177) & m
    h = (h ^ (h >> 16)) & m
    return (h % 1000003) / 1000003.0


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def value_noise(x, y, seed=0):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx, fy = x - x0, y - y0
    ux, uy = _smooth(fx), _smooth(fy)
    x0 = x0.astype(np.int64)
    y0 = y0.astype(np.int64)
    n00 = _hash01(x0, y0, seed)
    n10 = _hash01(x0 + 1, y0, seed)
    n01 = _hash01(x0, y0 + 1, seed)
    n11 = _hash01(x0 + 1, y0 + 1, seed)
    nx0 = n00 + (n10 - n00) * ux
    nx1 = n01 + (n11 - n01) * ux
    return nx0 + (nx1 - nx0) * uy


def fbm(x, y, octaves=6, base=4.0, seed=0, gain=0.5, lac=2.0):
    total = np.zeros_like(np.asarray(x, float))
    amp, norm, f = 1.0, 0.0, float(base)
    for o in range(int(octaves)):
        total = total + amp * value_noise(np.asarray(x) * f,
                                          np.asarray(y) * f, seed + o * 131)
        norm += amp
        amp *= gain
        f *= lac
    return total / max(norm, 1e-9)


def ridged(x, y, octaves=5, base=4.0, seed=0):
    n = fbm(x, y, octaves, base, seed)
    return 1.0 - np.abs(2.0 * n - 1.0)


# ------------------------------------------------------------------ styles
STYLES = {
    "default": {"a": (120, 122, 128), "b": (170, 172, 178), "rough": 0.6},
    "rock":    {"a": (74, 70, 66),    "b": (150, 144, 136), "rough": 0.85},
    "metal":   {"a": (96, 104, 118),  "b": (196, 208, 224), "rough": 0.25},
    "wood":    {"a": (78, 52, 30),    "b": (168, 120, 66),  "rough": 0.7},
    "grass":   {"a": (36, 76, 30),    "b": (128, 186, 74),  "rough": 0.75},
    "fabric":  {"a": (58, 62, 74),    "b": (128, 132, 146), "rough": 0.9},
    "hull":    {"a": (168, 172, 178), "b": (232, 236, 242), "rough": 0.35},
    "spiderman": {"a": (196, 28, 36), "b": (26, 58, 168), "rough": 0.4},
    "web":     {"a": (196, 28, 36), "b": (26, 58, 168), "rough": 0.4},
}


def _mix(c1, c2, t):
    c1 = np.asarray(c1, float)
    c2 = np.asarray(c2, float)
    t = np.asarray(t, float)[..., None]
    return c1 + (c2 - c1) * t


# ------------------------------------------------------------------ backends
def _gen_web(gx, gy, seed=7, grain=8.0, cells=6.0):
    """Spider-suit look: red webbed base, dark web lines, blue panels.
    Sampled in global coords, so it stays seamless across tiles."""
    cx, cy = gx * cells, gy * cells
    ix, iy = np.floor(cx), np.floor(cy)
    fx, fy = cx - ix - 0.5, cy - iy - 0.5
    r = np.sqrt(fx * fx + fy * fy)
    th = np.arctan2(fy, fx)
    jit = _hash01(ix, iy, seed) * 0.6
    spoke = np.abs(np.sin(th * 6.0 + jit))
    ring = np.abs(np.sin(r * 13.0 + jit * 2.0))
    web = np.minimum(spoke, ring)
    dark = np.clip((0.17 - web) / 0.17, 0, 1)
    b = fbm(gx, gy, octaves=4, base=2.2, seed=seed + 5)
    blue = np.clip((b - 0.56) / 0.12, 0, 1)
    red_c = np.array([196.0, 28.0, 36.0])
    blue_c = np.array([26.0, 58.0, 168.0])
    dark_c = np.array([16.0, 14.0, 18.0])
    base = red_c * (1 - blue[..., None]) + blue_c * blue[..., None]
    out = base * (1 - dark[..., None]) + dark_c * dark[..., None]
    sh = fbm(gx * 2.5, gy * 2.5, octaves=5, base=6.0, seed=seed + 11)
    out = out * (0.82 + 0.34 * sh[..., None])
    g = (_hash01(np.floor(gx * 1024).astype(np.int64),
                 np.floor(gy * 1024).astype(np.int64), seed + 3) - 0.5) * grain
    return np.clip(out + g[..., None], 0, 255).astype(np.uint8)


def gen_procedural(rect, ctx, res):
    x0, y0, x1, y1 = rect
    yy, xx = np.mgrid[y0:y1, x0:x1]
    gx, gy = xx / float(res), yy / float(res)
    style = ctx.get("style", "default")
    seed = ctx.get("seed", 7)
    if style in ("spiderman", "spider", "web"):
        return _gen_web(gx, gy, seed, float(ctx.get("grain", 8.0)))
    st = STYLES.get(style, STYLES["default"])
    fine = fbm(gx, gy, octaves=7, base=float(ctx.get("freq", 5.0)), seed=seed)
    veins = ridged(gx * 2.0, gy * 2.0, octaves=4, base=6.0, seed=seed + 91)
    h = np.clip(0.65 * fine + 0.35 * veins, 0, 1)
    rgb = _mix(st["a"], st["b"], h)
    grain = (_hash01(xx, yy, seed + 17) - 0.5) * float(ctx.get("grain", 10.0))
    return np.clip(rgb + grain[..., None], 0, 255).astype(np.uint8)


def gen_grounded(rect, ctx, res):
    src = np.asarray(ctx["source"], np.uint8)
    sh, sw = src.shape[:2]
    x0, y0, x1, y1 = rect
    yy, xx = np.mgrid[y0:y1, x0:x1]
    sx = (xx * sw // res) % sw
    sy = (yy * sh // res) % sh
    return src[sy, sx]


def gen_ai(rect, ctx, res):
    ai = ctx.get("ai")
    if not callable(ai):
        return gen_procedural(rect, ctx, res)
    try:
        out = ai(rect, ctx.get("prompt", ""), res)
        if out is None:
            return gen_procedural(rect, ctx, res)
        arr = np.asarray(out, np.uint8) if not hasattr(out, "size") \
            else np.asarray(out, np.uint8)
        h, w = rect[3] - rect[1], rect[2] - rect[0]
        if arr.shape[0] != h or arr.shape[1] != w:
            arr = _linspace_img(arr, w, h)
        return arr
    except Exception:
        return gen_procedural(rect, ctx, res)


BACKENDS = {"procedural": gen_procedural, "grounded": gen_grounded,
            "ai": gen_ai}


# ------------------------------------------------------------------ tiling
def plan_tiles(res, tile, overlap):
    step = max(1, tile - overlap)
    tiles = []
    y = 0
    while True:
        x = 0
        while True:
            tiles.append((x, y, min(x + tile, res), min(y + tile, res)))
            if x + tile >= res:
                break
            x += step
        if y + tile >= res:
            break
        y += step
    return tiles


def _window(h, w, overlap):
    wx = np.ones(w)
    wy = np.ones(h)
    if overlap > 0:
        r = min(overlap, w // 2)
        if r > 0:
            ramp = np.sin(np.linspace(0, np.pi / 2, r)) ** 2
            wx[:r] = ramp
            wx[-r:] = ramp[::-1]
        r = min(overlap, h // 2)
        if r > 0:
            ramp = np.sin(np.linspace(0, np.pi / 2, r)) ** 2
            wy[:r] = ramp
            wy[-r:] = ramp[::-1]
    return np.outer(wy, wx)


def stitch(rects, imgs, res, overlap):
    acc = np.zeros((res, res, 3), float)
    wsum = np.zeros((res, res), float)
    for (x0, y0, x1, y1), img in zip(rects, imgs):
        h, w = y1 - y0, x1 - x0
        win = _window(h, w, overlap)
        acc[y0:y1, x0:x1] += np.asarray(img, float) * win[..., None]
        wsum[y0:y1, x0:x1] += win
    wsum = np.maximum(wsum, 1e-6)
    return np.clip(acc / wsum[..., None], 0, 255).astype(np.uint8)


def synthesize(res, tile=512, overlap=64, backend="procedural", band=1024,
               **ctx):
    """Generate + stitch the whole texture, band-by-band so 8K/16K stay
    within memory (accumulator is only band x res, not res x res)."""
    fn = BACKENDS.get(backend, gen_procedural)
    ctx.setdefault("seed", 7)
    ctx.setdefault("style", "default")
    ctx["res"] = res
    rects = plan_tiles(res, tile, overlap)
    band = int(max(tile, min(res, band)))
    out = np.zeros((res, res, 3), np.uint8)
    for by0 in range(0, res, band):
        by1 = min(by0 + band, res)
        bh = by1 - by0
        acc = np.zeros((bh, res, 3), np.float32)
        wsum = np.zeros((bh, res), np.float32)
        for (x0, y0, x1, y1) in rects:
            if y1 <= by0 or y0 >= by1:
                continue
            img = np.asarray(fn((x0, y0, x1, y1), ctx, res), np.float32)
            win = _window(y1 - y0, x1 - x0, overlap)
            ty0, ty1 = max(y0, by0), min(y1, by1)
            sy0 = ty0 - y0
            k = ty1 - ty0
            acc[ty0 - by0:ty1 - by0, x0:x1] += \
                img[sy0:sy0 + k] * win[sy0:sy0 + k][..., None]
            wsum[ty0 - by0:ty1 - by0, x0:x1] += win[sy0:sy0 + k]
        out[by0:by1] = np.clip(
            acc / np.maximum(wsum, 1e-6)[..., None], 0, 255).astype(np.uint8)
    return out, rects


# ------------------------------------------------------------------ detail
def unsharp(img, amount=1.0, radius=2.0, threshold=0):
    from PIL import Image, ImageFilter
    im = Image.fromarray(np.asarray(img, np.uint8))
    blur = im.filter(ImageFilter.GaussianBlur(radius))
    a = np.asarray(im, float)
    b = np.asarray(blur, float)
    diff = a - b
    if threshold:
        diff = np.where(np.abs(diff) < threshold, 0, diff)
    return np.clip(a + amount * diff, 0, 255).astype(np.uint8)


def add_detail(img, amount=0.35, seed=1, scale=1.0):
    a = np.asarray(img, float)
    h, w = a.shape[:2]
    rng = np.random.default_rng(seed)
    noise = rng.random((h, w, 1)) - 0.5
    lum = a.mean(axis=2, keepdims=True) / 255.0
    edge = np.abs(np.gradient(a.mean(axis=2))[0]) + \
        np.abs(np.gradient(a.mean(axis=2))[1])
    edge = np.clip(edge / (edge.max() + 1e-6), 0, 1)[..., None]
    boost = (0.4 + 1.6 * edge) * amount * 255.0 * scale
    return np.clip(a + noise * boost, 0, 255).astype(np.uint8)


def super_res(img, factor=2):
    """Upscale with LANCZOS then re-inject high-frequency detail."""
    from PIL import Image
    a = np.asarray(img, np.uint8)
    if factor <= 1:
        return a
    h, w = a.shape[:2]
    up = np.asarray(Image.fromarray(a).resize((w * factor, h * factor),
                                              Image.LANCZOS))
    up = unsharp(up, amount=0.8, radius=1.2)
    return add_detail(up, amount=0.18, seed=int(w + h), scale=1.0)


# ------------------------------------------------------------------ bake
def rasterize_atlas(uv, faces, res, attr):
    """Write a per-vertex attribute into the UV atlas (barycentric)."""
    out = np.zeros((res, res), float)
    mask = np.zeros((res, res), bool)
    uv = np.asarray(uv, float) * (res - 1)
    faces = np.asarray(faces, int)
    attr = np.asarray(attr, float)
    for f in faces:
        p = uv[f]
        minx = max(int(np.floor(p[:, 0].min())), 0)
        maxx = min(int(np.ceil(p[:, 0].max())), res - 1)
        miny = max(int(np.floor(p[:, 1].min())), 0)
        maxy = min(int(np.ceil(p[:, 1].max())), res - 1)
        if maxx < minx or maxy < miny:
            continue
        xs = np.arange(minx, maxx + 1)
        ys = np.arange(miny, maxy + 1)
        gx, gy = np.meshgrid(xs, ys)
        x0, y0 = p[0]
        x1, y1 = p[1]
        x2, y2 = p[2]
        det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(det) < 1e-9:
            continue
        w0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / det
        w1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / det
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -0.002) & (w1 >= -0.002) & (w2 >= -0.002)
        if not inside.any():
            continue
        val = w0 * attr[f[0]] + w1 * attr[f[1]] + w2 * attr[f[2]]
        sub = out[miny:maxy + 1, minx:maxx + 1]
        smask = mask[miny:maxy + 1, minx:maxx + 1]
        sub[inside] = val[inside]
        smask[inside] = True
    return out, mask


def bake_curvature(V, F):
    """Per-vertex discrete mean curvature magnitude (0..1)."""
    V = np.asarray(V, float)
    F = np.asarray(F, int)
    nbr = [[] for _ in range(len(V))]
    for f in F:
        n = len(f)
        for i in range(n):
            nbr[f[i]].append(f[(i + 1) % n])
            nbr[f[i]].append(f[(i - 1) % n])
    k = np.zeros(len(V))
    for i, ns in enumerate(nbr):
        if not ns:
            continue
        lap = V[ns].mean(axis=0) - V[i]
        k[i] = np.linalg.norm(lap)
    rng = k.max() - k.min()
    return (k - k.min()) / (rng + 1e-9)


def bake_ao(V, F, samples=24, dist=None, seed=3):
    """Approximate ambient occlusion per vertex by hemisphere ray casting."""
    import trimesh
    from trimesh.ray.ray_triangle import RayMeshIntersector
    V = np.asarray(V, float)
    F = np.asarray(F, int)
    tm = trimesh.Trimesh(vertices=V, faces=F, process=False)
    try:
        normals = np.asarray(tm.vertex_normals, float)
    except Exception:
        return np.ones(len(V))
    inter = RayMeshIntersector(tm)
    diag = float(np.linalg.norm(V.max(axis=0) - V.min(axis=0))) or 1.0
    ray_len = dist or (diag * 0.5)
    rng = np.random.default_rng(seed)
    ao = np.ones(len(V))
    origins_all = V
    for i in range(len(V)):
        n = normals[i]
        if not np.isfinite(n).all() or np.linalg.norm(n) < 1e-9:
            continue
        n = n / np.linalg.norm(n)
        t = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else \
            np.array([0.0, 1.0, 0.0])
        b1 = np.cross(n, t)
        b1 /= (np.linalg.norm(b1) + 1e-9)
        b2 = np.cross(n, b1)
        u = rng.random(samples)
        v = rng.random(samples)
        r = np.sqrt(u)
        phi = 2 * np.pi * v
        dirs = (n[None, :] * np.sqrt(np.maximum(0, 1 - u))[:, None] +
                b1[None, :] * (r * np.cos(phi))[:, None] +
                b2[None, :] * (r * np.sin(phi))[:, None])
        origins = np.repeat(origins_all[i][None, :], samples, axis=0) + \
            n[None, :] * 1e-4
        try:
            loc, _idx, _ = inter.intersects_location(
                origins, dirs, multiple_hits=False)
            hits = len(np.unique(_idx))
        except Exception:
            hits = 0
        ao[i] = 1.0 - (hits / float(samples)) * 0.85
    return np.clip(ao, 0, 1)


def height_to_normal(height, strength=2.0):
    h = np.asarray(height, float) / 255.0
    gy, gx = np.gradient(h)
    nx = -gx * strength * 255.0
    ny = -gy * strength * 255.0
    nz = np.ones_like(h)
    n = np.stack([nx, ny, nz], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
    return np.clip((n * 0.5 + 0.5) * 255, 0, 255).astype(np.uint8)


STYLE_METAL = {"metal": 0.9, "hull": 0.55, "default": 0.1, "rock": 0.0,
               "wood": 0.0, "grass": 0.0, "fabric": 0.0,
               "spiderman": 0.05, "web": 0.05}


def normal_from_albedo(albedo, strength=0.6, blur=1.2):
    """Derive a tangent-space normal map from albedo detail (high-pass)."""
    from PIL import Image, ImageFilter
    g = Image.fromarray(np.asarray(albedo, np.uint8)).convert("L")
    low = g.filter(ImageFilter.GaussianBlur(blur))
    hp = np.asarray(g, float) - np.asarray(low, float)
    gy, gx = np.gradient(hp)
    nx = -gx * strength
    ny = -gy * strength
    nz = np.ones_like(hp)
    n = np.stack([nx, ny, nz], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
    return np.clip((n * 0.5 + 0.5) * 255, 0, 255).astype(np.uint8)


def combine_normals(n1, n2, w=0.5):
    """Blend two tangent-space normal maps (geometry + detail)."""
    a = np.asarray(n1, float) / 127.5 - 1.0
    b = np.asarray(n2, float) / 127.5 - 1.0
    n = a * (1.0 - w) + b * w
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
    return np.clip((n * 0.5 + 0.5) * 255, 0, 255).astype(np.uint8)


def pack_orm(ao, roughness, metallic):
    """glTF ORM: R=occlusion, G=roughness, B=metallic."""
    a = np.asarray(ao, np.uint8)
    r = np.asarray(roughness, np.uint8)
    m = np.asarray(metallic, np.uint8)
    if m.ndim == 0:
        m = np.full_like(a, int(m))
    return np.stack([a, r, m], axis=-1).astype(np.uint8)


def bake_maps(uv, faces, res, V, F, do_ao=True, ao_samples=24, albedo=None,
              metal=0.0):
    """Bake curvature, AO, tangent-space normal (geometry + albedo detail),
    roughness and a packed ORM map for the atlas."""
    maps = {}
    curv, _ = rasterize_atlas(uv, faces, res, bake_curvature(V, F))
    maps["curvature"] = np.clip(curv * 255, 0, 255).astype(np.uint8)
    if do_ao:
        try:
            ao = bake_ao(V, F, samples=ao_samples)
            a, _ = rasterize_atlas(uv, faces, res, ao)
        except Exception:
            a = np.ones((res, res))
    else:
        a = np.ones((res, res))
    maps["ao"] = np.clip(a * 255, 0, 255).astype(np.uint8)
    n_geo = height_to_normal(maps["curvature"], strength=1.4)
    if albedo is not None:
        n_det = normal_from_albedo(albedo, strength=0.6)
        maps["normal"] = combine_normals(n_geo, n_det, w=0.5)
    else:
        maps["normal"] = n_geo
    rough = 0.55 + 0.4 * (1.0 - maps["curvature"].astype(float) / 255.0)
    rough *= (0.6 + 0.4 * maps["ao"].astype(float) / 255.0)
    maps["roughness"] = np.clip(rough * 255, 0, 255).astype(np.uint8)
    maps["orm"] = pack_orm(maps["ao"], maps["roughness"],
                           np.full((res, res), int(metal * 255), np.uint8))
    return maps


# ------------------------------------------------------------------ apply
def apply_texture(V, F, uvs, albedo_png, base, formats=("glb", "obj", "fbx"),
                  map_paths=None):
    """Build a textured mesh and export. Wires normal / ORM / occlusion into
    the glTF material when those maps are supplied."""
    import trimesh
    from PIL import Image
    from trimesh.visual import TextureVisuals
    from trimesh.visual.material import PBRMaterial
    tm = trimesh.Trimesh(vertices=np.asarray(V, float),
                         faces=np.asarray(F, int), process=False)
    img = Image.open(albedo_png).convert("RGB")
    kwargs = dict(baseColorTexture=img, metallicFactor=0.0, roughnessFactor=0.6)
    if map_paths:
        if map_paths.get("normal"):
            kwargs["normalTexture"] = Image.open(
                map_paths["normal"]).convert("RGB")
        if map_paths.get("orm"):
            kwargs["metallicRoughnessTexture"] = Image.open(
                map_paths["orm"]).convert("RGB")
            kwargs["metallicFactor"] = 1.0
            kwargs["roughnessFactor"] = 1.0
        if map_paths.get("ao"):
            kwargs["occlusionTexture"] = Image.open(
                map_paths["ao"]).convert("RGB")
    tm.visual = TextureVisuals(uv=np.asarray(uvs, float),
                               material=PBRMaterial(**kwargs))
    outs = {}
    want = [f.lstrip(".").lower() for f in formats]
    if "glb" in want or "fbx" in want or "usdz" in want:
        glb = base + ".glb"
        tm.export(glb)
        outs["glb"] = glb
    if "obj" in want:
        obj = base + ".obj"
        tm.export(obj, file_type="obj")
        outs["obj"] = obj
    if "gltf" in want:
        gltf = base + ".gltf"
        tm.export(gltf, file_type="gltf")
        outs["gltf"] = gltf
    special = [f for f in want if f in ("fbx", "usdz", "usd")]
    if special:
        src = outs.get("glb") or base + ".glb"
        if not os.path.exists(src):
            tm.export(src)
        outs.update(threed.blender_export(src, base, special))
    return outs


# ------------------------------------------------------------------ parts
def split_parts(mesh, max_parts=64):
    """Split a mesh into connected components (its natural 'parts')."""
    import trimesh
    V, F = _np_mesh(mesh)
    F = triangulate(F)
    tm = trimesh.Trimesh(vertices=V, faces=F, process=False)
    try:
        comps = tm.split(only_watertight=False)
    except Exception:
        return [mesh]
    comps = [c for c in comps if len(c.faces) > 0][:max_parts]
    return [_mesh(np.asarray(c.vertices, float), np.asarray(c.faces, int),
                  f"{mesh.name}-p{i}") for i, c in enumerate(comps)]


# ------------------------------------------------------------------ ai seeds
def quilt_from_seeds(seeds, res, patch=256, overlap=64, cand=24, seed=0):
    """Build a full texture from a few AI seed images by image-quilting:
    each output patch is the best-matching random crop (SSD over the
    overlap with already-placed neighbours), then feathered in. This gives
    a non-repeating, seam-light result from just a handful of AI tiles."""
    rng = np.random.default_rng(seed)
    seeds = [np.asarray(s, np.uint8) for s in seeds if s is not None]
    if not seeds:
        return None
    out = np.zeros((res, res, 3), np.float32)
    placed = np.zeros((res, res), bool)
    step = max(1, patch - overlap)
    for y in range(0, res, step):
        for x in range(0, res, step):
            h, w = min(patch, res - y), min(patch, res - x)
            best, best_score = None, None
            for _ in range(cand):
                s = seeds[int(rng.integers(len(seeds)))]
                sh, sw = s.shape[:2]
                py = int(rng.integers(0, max(1, sh - h)))
                px = int(rng.integers(0, max(1, sw - w)))
                crop = s[py:py + h, px:px + w].astype(np.float32)
                if crop.shape[:2] != (h, w):
                    continue
                score = 0.0
                if x > 0 and placed[y:y + h, x - 1].any():
                    score += float(np.mean(
                        (out[y:y + h, x:x + overlap] -
                         crop[:, :overlap]) ** 2))
                if y > 0 and placed[y - 1, x:x + w].any():
                    score += float(np.mean(
                        (out[y:y + overlap, x:x + w] -
                         crop[:overlap]) ** 2))
                if best_score is None or score < best_score:
                    best_score, best = score, crop
            if best is None:
                continue
            out[y:y + h, x:x + w] = best
            placed[y:y + h, x:x + w] = True
            # feather the seams with existing content
            if x > 0:
                a = np.linspace(0.0, 1.0, overlap, dtype=np.float32)[None, :, None]
                col = out[y:y + h, x:x + overlap]
                out[y:y + h, x:x + overlap] = \
                    col * (1 - a) + best[:, :overlap] * a
            if y > 0:
                a = np.linspace(0.0, 1.0, overlap, dtype=np.float32)[:, None, None]
                row = out[y:y + overlap, x:x + w]
                out[y:y + overlap, x:x + w] = \
                    row * (1 - a) + best[:overlap] * a
    return np.clip(out, 0, 255).astype(np.uint8)


def ai_source(prompt, res, tile=512, model=None, steps=4, n_seeds=3, seed=0,
              cache_dir=None):
    """Generate AI seed tiles on the accelerator, then quilt them into a
    full-resolution source image. Returns (image_or_None, info)."""
    import compute
    model = model or compute.pick_model()
    if model == "procedural":
        return None, {"model": "procedural", "reason": "no AI model present"}
    import tempfile
    from PIL import Image
    cdir = cache_dir or tempfile.gettempdir()
    os.makedirs(cdir, exist_ok=True)
    seeds = []
    for k in range(int(n_seeds)):
        out = os.path.join(cdir, f"coal_ai_{model}_{seed}_{k}.png")
        r = compute.sd_generate(prompt, out=out, model=model,
                                   steps=steps, seed=seed + k, size=tile)
        if not r.get("ok"):
            return None, {"model": model, "error": r.get("error", "failed")}
        seeds.append(np.asarray(Image.open(out).convert("RGB")))
    img = quilt_from_seeds(seeds, res, patch=min(256, tile), overlap=64,
                           seed=seed)
    return img, {"model": model, "seeds": int(n_seeds), "res": res,
                 "prompt": prompt}


# ------------------------------------------------------------------ top level
def texture_mesh(mesh, outdir, name=None, resolution=2048, tile=512,
                 overlap=64, backend="procedural", style="default",
                 prompt="", source=None, ai=None, maps=True, ao_samples=24,
                 detail=True, sharpen=0.8, parts=False, band=1024,
                 detail_normal=True, mipmaps=0,
                 ai_prompt=None, ai_model=None, ai_steps=4, ai_seeds=3,
                 formats=("glb", "obj", "fbx"), seed=7):
    """Full texturing run. Returns dict(files, maps, stats)."""
    os.makedirs(outdir, exist_ok=True)
    nm = name or mesh.name or "model"
    uw = unwrap(mesh, res=resolution)
    ai_info = None
    if ai_prompt:
        try:
            src, ai_info = ai_source(ai_prompt, resolution, tile=tile,
                                     model=ai_model, steps=ai_steps,
                                     n_seeds=ai_seeds, seed=seed,
                                     cache_dir=outdir)
            if src is not None:
                source = src
                backend = "grounded"
        except Exception as e:
            ai_info = {"error": str(e)[:200]}
    ctx = {"style": style, "seed": seed, "prompt": prompt, "source": source,
           "ai": ai, "freq": 5.0, "grain": 9.0, "octaves": 7}
    albedo, rects = synthesize(resolution, tile=tile, overlap=overlap,
                               backend=backend, band=band, **ctx)
    if sharpen:
        albedo = unsharp(albedo, amount=sharpen, radius=1.6)
    if detail:
        albedo = add_detail(albedo, amount=0.22, seed=seed)
    base = os.path.join(outdir, nm)
    files = {}
    files["albedo"] = _save_png(albedo, base + "-albedo.png")
    maps_out = {}
    if maps:
        m = bake_maps(uw["uvs"], uw["faces"], resolution,
                      uw["vertices"], uw["faces"], ao_samples=ao_samples,
                      albedo=albedo if detail_normal else None,
                      metal=STYLE_METAL.get(style, 0.0))
        for k, v in m.items():
            maps_out[k] = _save_png(v, f"{base}-{k}.png")
    if mipmaps:
        files["mipmaps"] = write_mipmaps(albedo, base, levels=mipmaps)
    files.update(apply_texture(
        uw["vertices"], uw["faces"], uw["uvs"], files["albedo"], base,
        formats=list(formats),
        map_paths={k: maps_out[k] for k in ("normal", "orm", "ao")
                   if k in maps_out}))
    try:                                   # visible textured preview
        uwm = _mesh(uw["vertices"], uw["faces"], nm)
        files["textured_png"] = threed.render_textured_png(
            uwm, uw["uvs"], files["albedo"], base + "-textured.png")
    except Exception:
        pass
    files.update(maps_out)
    return {"files": files, "stats": {
        "name": nm, "resolution": resolution, "tile": tile,
        "tiles": len(rects), "textured_triangles": int(len(uw["faces"])),
        "backend": backend, "style": style,
        "metal": STYLE_METAL.get(style, 0.0), "ai": ai_info},
        "parts": parts}


def texture_parts(mesh, outdir, **opts):
    """Unwrap + texture each connected part separately, then combine."""
    os.makedirs(outdir, exist_ok=True)
    parts = split_parts(mesh)
    results = []
    for i, p in enumerate(parts):
        r = texture_mesh(p, outdir, name=f"{mesh.name}-p{i}", **opts)
        results.append(r)
    return {"parts": len(parts), "results": results}


def backends_info():
    return {"backends": sorted(BACKENDS),
            "styles": sorted(STYLES),
            "note": "procedural is dependency-free; grounded needs a source "
                    "image; ai accepts a per-tile callable (local SD / API)."}


if __name__ == "__main__":
    import json
    print(json.dumps(backends_info(), indent=1))
