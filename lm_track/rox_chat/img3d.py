"""ROX N image -> 3D.

Turns a picture into a mesh. Three CPU-feasible methods (no GPU needed):

    relief      depth from luminance -> displaced grid; UV = the image, so
                the photo becomes the texture exactly.
    silhouette  cut the subject out (alpha or border-colour flood), then
                extrude the cut-out into a real slab/relief.
    depth       use an external depth map (e.g. an AI monocular-depth model
                running as a pluggable backend) to displace the grid.

Every method returns (mesh, texture_png) ready for the texturing engine.
"""
from __future__ import annotations

import os

import numpy as np

import threed


def load_image(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"), np.uint8)


def auto_mask(img, tol=30):
    """Foreground mask: alpha if present, else border-colour flood."""
    a = np.asarray(img)
    if a.shape[2] == 4 and a[..., 3].min() < 250:
        return (a[..., 3] > 16).astype(np.uint8)
    rgb = a[..., :3].astype(np.int16)
    h, w = rgb.shape[:2]
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
    similar = dist < tol
    try:
        from scipy import ndimage
        lab, n = ndimage.label(similar)
        edge_labels = set(lab[0]) | set(lab[-1]) | set(lab[:, 0]) | \
            set(lab[:, -1])
        edge_labels.discard(0)
        bgmask = np.isin(lab, list(edge_labels))
    except Exception:
        bgmask = similar
    return (~bgmask).astype(np.uint8)


def _grid_mesh(size, depth_map, texture, name="relief", depth_scale=1.0,
               xy_scale=2.0):
    """Build a displaced grid mesh; UV maps the texture 1:1."""
    size = int(size)
    h = w = size
    dm = np.asarray(depth_map, float)
    if dm.shape != (h, w):
        from PIL import Image
        dm = np.asarray(Image.fromarray(
            (np.clip(dm, 0, 1) * 255).astype(np.uint8)).resize(
            (w, h), Image.BILINEAR), float) / 255.0
    xs = np.linspace(-xy_scale / 2, xy_scale / 2, w)
    ys = np.linspace(-xy_scale / 2, xy_scale / 2, h)
    gx, gy = np.meshgrid(xs, ys)
    z = (dm * depth_scale)
    verts = np.stack([gx.ravel(), z.ravel() * 0 + gy.ravel(), z.ravel()],
                     axis=1)
    uvs = np.stack([gx.ravel() / xy_scale + 0.5,
                    1.0 - (gy.ravel() / xy_scale + 0.5)], axis=1)
    faces = []
    for j in range(h - 1):
        for i in range(w - 1):
            a = j * w + i
            b = a + 1
            c = a + w
            d = c + 1
            faces.append((a, c, d))
            faces.append((a, d, b))
    return threed.Mesh([tuple(v) for v in verts], faces, name), uvs


def relief(img, size=192, depth_scale=0.6, invert=False, name="relief"):
    """Luminance -> height. Brighter = higher (or inverted)."""
    from PIL import Image
    rgb = Image.fromarray(np.asarray(img)[..., :3]).convert("L").resize(
        (size, size), Image.LANCZOS)
    lum = np.asarray(rgb, float) / 255.0
    if invert:
        lum = 1.0 - lum
    lum = 0.15 + 0.85 * lum
    return _grid_mesh(size, lum, img, name=name, depth_scale=depth_scale)


def silhouette(img, size=192, thickness=0.5, depth_scale=1.0, invert=False,
               name="silhouette"):
    """Cut out the subject, then extrude it into a slab-relief."""
    from PIL import Image
    mask = auto_mask(img)
    m = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).resize(
        (size, size), Image.LANCZOS), float) / 255.0
    m = (m > 0.5).astype(float)
    rgb = Image.fromarray(np.asarray(img)[..., :3]).convert("L").resize(
        (size, size), Image.LANCZOS)
    lum = np.asarray(rgb, float) / 255.0
    depth = m * (0.35 + 0.65 * lum) * thickness
    if invert:
        depth = m * thickness - depth
    return _grid_mesh(size, depth, img, name=name, depth_scale=1.0)


def depth_relief(depth_map, texture, size=192, depth_scale=0.6,
                 name="depth3d"):
    """Displace a grid by an external depth map (AI depth backend output)."""
    dm = np.asarray(depth_map, float)
    dm = (dm - dm.min()) / (dm.max() - dm.min() + 1e-9)
    return _grid_mesh(size, dm, texture, name=name, depth_scale=depth_scale)


METHODS = {"relief": relief, "silhouette": silhouette}


def image_to_3d(path, outdir, method="relief", size=192, depth_scale=0.6,
                name=None, formats=("obj", "stl", "gltf", "png"),
                depth_map=None, invert=False):
    """Full image->3D run. Returns dict(files, stats)."""
    from PIL import Image
    os.makedirs(outdir, exist_ok=True)
    img = load_image(path)
    nm = name or os.path.splitext(os.path.basename(path))[0] or "image3d"
    if method == "depth" and depth_map is not None:
        mesh, uvs = depth_relief(depth_map, img, size=size,
                                 depth_scale=depth_scale, name=nm)
    else:
        fn = METHODS.get(method, relief)
        mesh, uvs = fn(img, size=size, depth_scale=depth_scale, invert=invert,
                       name=nm)
    base = os.path.join(outdir, nm)
    files = {}
    files["obj"] = threed.write_obj(mesh, base + ".obj")
    files["stl"] = threed.write_stl(mesh, base + ".stl")
    files["gltf"] = threed.write_gltf(mesh, base + ".gltf")
    files["png"] = threed.render_png(mesh, base + ".png")
    tex = base + "-texture.png"
    Image.fromarray(np.asarray(img)[..., :3]).save(tex)
    files["texture"] = tex
    return {"files": files, "uvs": uvs, "mesh": mesh,
            "stats": {**mesh.stats(), "method": method, "size": size}}


def backends_info():
    return {"methods": sorted(METHODS) + ["depth"],
            "note": "relief/silhouette are dependency-light; 'depth' takes a "
                    "depth-map path or an AI monocular-depth backend."}


if __name__ == "__main__":
    import json
    print(json.dumps(backends_info(), indent=1))
