"""Coal 3D — procedural & parametric mesh generation, export and preview.

Pure-Python (stdlib + numpy + Pillow). Produces Wavefront OBJ, binary STL,
and a shaded PNG preview. Supports primitives, a procedural terrain, and a
primitive-graph spec (optionally produced by the local model from a text
description) so Coal can 'generate 3D models'.

    from threed import generate
    paths = generate(outdir, shape="torus", R=1.0, r=0.3)
    paths = generate(outdir, description="a low-poly rocket", spec=spec)
"""
from __future__ import annotations

import json
import math
import os
import struct
import time


class Mesh:
    def __init__(self, verts=None, faces=None, name="model"):
        self.verts = list(verts or [])
        self.faces = list(faces or [])
        self.name = name

    def add(self, other, offset=(0.0, 0.0, 0.0)):
        base = len(self.verts)
        ox, oy, oz = offset
        self.verts += [(x + ox, y + oy, z + oz) for (x, y, z) in other.verts]
        self.faces += [tuple(i + base for i in f) for f in other.faces]
        return self

    def scaled(self, s):
        self.verts = [(x * s, y * s, z * s) for (x, y, z) in self.verts]
        return self

    def bounds(self):
        if not self.verts:
            return (0, 0, 0, 0, 0, 0)
        xs = [v[0] for v in self.verts]
        ys = [v[1] for v in self.verts]
        zs = [v[2] for v in self.verts]
        return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))

    def stats(self):
        x0, y0, z0, x1, y1, z1 = self.bounds()
        return {"name": self.name, "vertices": len(self.verts),
                "faces": len(self.faces),
                "size": [round(x1 - x0, 3), round(y1 - y0, 3),
                         round(z1 - z0, 3)]}


# ---------------------------------------------------------------- primitives
def box(sx=1.0, sy=1.0, sz=1.0, **_):
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    v = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
         (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    f = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2),
         (2, 6, 7, 3), (3, 7, 4, 0)]
    return Mesh(v, f, "box")


def pyramid(base=1.0, h=1.0, **_):
    hb = base / 2
    v = [(-hb, 0, -hb), (hb, 0, -hb), (hb, 0, hb), (-hb, 0, hb),
         (0, h, 0)]
    f = [(0, 1, 2, 3), (0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0)]
    return Mesh(v, f, "pyramid")


def cylinder(r=0.5, h=1.0, seg=24, **_):
    v, f = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        v.append((r * math.cos(a), 0, r * math.sin(a)))
    for i in range(seg):
        a = 2 * math.pi * i / seg
        v.append((r * math.cos(a), h, r * math.sin(a)))
    for i in range(seg):
        j = (i + 1) % seg
        f.append((i, j, j + seg, i + seg))
    cb, ct = len(v), len(v) + 1
    v += [(0, 0, 0), (0, h, 0)]
    for i in range(seg):
        j = (i + 1) % seg
        f.append((cb, j, i))
        f.append((ct, i + seg, j + seg))
    return Mesh(v, f, "cylinder")


def sphere(r=1.0, seg=24, rings=12, **_):
    v, f = [], []
    for y in range(rings + 1):
        phi = math.pi * y / rings
        for x in range(seg):
            th = 2 * math.pi * x / seg
            v.append((r * math.sin(phi) * math.cos(th),
                      r * math.cos(phi),
                      r * math.sin(phi) * math.sin(th)))
    for y in range(rings):
        for x in range(seg):
            a = y * seg + x
            b = y * seg + (x + 1) % seg
            c = (y + 1) * seg + x
            d = (y + 1) * seg + (x + 1) % seg
            f.append((a, b, d, c))
    return Mesh(v, f, "sphere")


def torus(R=1.0, r=0.3, seg=32, tube=12, **_):
    v, f = [], []
    for i in range(seg):
        u = 2 * math.pi * i / seg
        for j in range(tube):
            w = 2 * math.pi * j / tube
            x = (R + r * math.cos(w)) * math.cos(u)
            z = (R + r * math.cos(w)) * math.sin(u)
            y = r * math.sin(w)
            v.append((x, y, z))
    for i in range(seg):
        for j in range(tube):
            a = i * tube + j
            b = ((i + 1) % seg) * tube + j
            c = ((i + 1) % seg) * tube + (j + 1) % tube
            d = i * tube + (j + 1) % tube
            f.append((a, b, c, d))
    return Mesh(v, f, "torus")


def cone(r=0.5, h=1.0, seg=24, **_):
    v, f = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        v.append((r * math.cos(a), 0, r * math.sin(a)))
    v.append((0, h, 0))
    apex = seg
    v.append((0, 0, 0))
    base = seg + 1
    for i in range(seg):
        j = (i + 1) % seg
        f.append((i, j, apex))
        f.append((base, j, i))
    return Mesh(v, f, "cone")


def _h(i, j):
    n = (i * 127 + j * 311) % 65536
    n = ((n ^ (n >> 4)) * 39221) & 0xFFFF
    return (n & 0xFFFF) / 65535.0


def _noise(x, y):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a, b = _h(ix, iy), _h(ix + 1, iy)
    c, d = _h(ix, iy + 1), _h(ix + 1, iy + 1)
    return (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy)
            + c * (1 - fx) * fy + d * fx * fy)


def terrain(size=32, scale=10.0, height=2.0, **_):
    v, f = [], []
    hs = [[_noise(x / 6.0, y / 6.0) * height for x in range(size + 1)]
          for y in range(size + 1)]
    for y in range(size + 1):
        for x in range(size + 1):
            v.append((x * scale / size, hs[y][x], y * scale / size))
    for y in range(size):
        for x in range(size):
            a = y * (size + 1) + x
            b, c, d = a + 1, a + (size + 1), a + (size + 1) + 1
            f.append((a, b, d))
            f.append((a, d, c))
    return Mesh(v, f, "terrain")


def man(scale=1.0, seg=6, **_):
    """Low-poly humanoid built from primitives (Y up, feet at y=0).

    Hexagonal limbs + box torso/head keep the triangle count low, which is
    exactly what 'low poly' means — flat-shaded, faceted, game-ready."""
    m = Mesh(name="low_poly_man")
    # torso / chest / pelvis
    m.add(box(1.10, 1.30, 0.55), (0.0, 2.30, 0.0))
    m.add(box(1.30, 0.35, 0.55), (0.0, 2.78, 0.0))     # shoulders
    m.add(box(0.95, 0.45, 0.50), (0.0, 1.42, 0.0))     # pelvis
    # neck + head
    m.add(cylinder(0.17, 0.22, seg), (0.0, 2.92, 0.0))
    m.add(box(0.52, 0.60, 0.52), (0.0, 3.16, 0.0))
    # arms (hang vertically)
    for sx in (-1, 1):
        m.add(cylinder(0.15, 0.70, seg), (sx * 0.72, 2.20, 0.0))
        m.add(cylinder(0.13, 0.62, seg), (sx * 0.72, 1.58, 0.0))
        m.add(box(0.20, 0.24, 0.13), (sx * 0.72, 1.52, 0.0))
    # legs
    for sx in (-1, 1):
        m.add(cylinder(0.21, 0.85, seg), (sx * 0.27, 0.57, 0.0))
        m.add(cylinder(0.17, 0.50, seg), (sx * 0.27, 0.07, 0.0))
        m.add(box(0.24, 0.12, 0.40), (sx * 0.27, 0.02, 0.10))
    if scale != 1.0:
        m.scaled(scale)
    return m


SHAPES = {"box": box, "pyramid": pyramid, "cylinder": cylinder,
          "sphere": sphere, "torus": torus, "cone": cone, "terrain": terrain,
          "man": man, "human": man, "person": man, "humanoid": man,
          "figure": man}


def make(shape="box", **kw):
    fn = SHAPES.get(shape)
    if not fn:
        raise ValueError(f"unknown shape: {shape}")
    allowed = {"size", "scale", "height", "seg", "rings", "tube", "R", "r",
               "h", "base", "sx", "sy", "sz"}
    p = {k: v for k, v in kw.items() if k in allowed}
    if shape == "box":
        p = {k: p.get(k, d) for k, d in
             (("sx", 1.0), ("sy", 1.0), ("sz", 1.0))}
    m = fn(**p)
    return m


# ---------------------------------------------------------------- spec graph
def build_from_spec(spec: dict) -> Mesh:
    """spec = {"name":.., "parts":[{"shape":..,"at":[x,y,z],"scale":s,..}]}"""
    mesh = Mesh(name=spec.get("name", "model"))
    parts = spec.get("parts") or [{"shape": "box"}]
    for p in parts:
        s = p.get("shape", "box")
        at = p.get("at", [0, 0, 0])
        kw = {k: v for k, v in p.items()
              if k not in ("shape", "at", "scale")}
        m = make(s, **kw)
        if p.get("scale"):
            m.scaled(float(p["scale"]))
        mesh.add(m, (float(at[0]), float(at[1]), float(at[2])))
    return mesh


HEURISTIC_PARTS = {
    "tree": [{"shape": "cylinder", "r": 0.15, "h": 1.0},
             {"shape": "sphere", "r": 0.6, "at": [0, 1.3, 0]}],
    "rocket": [{"shape": "cylinder", "r": 0.4, "h": 2.0},
               {"shape": "cone", "r": 0.4, "h": 0.8, "at": [0, 2.0, 0]}],
    "robot": [{"shape": "box", "sx": 0.8, "sy": 1.2, "sz": 0.5},
              {"shape": "box", "sx": 0.6, "sy": 0.6, "sz": 0.6,
               "at": [0, 1.1, 0]}],
    "house": [{"shape": "box", "sx": 1.6, "sy": 1.0, "sz": 1.2},
              {"shape": "pyramid", "base": 1.8, "h": 1.0, "at": [0, 1.0, 0]}],
    "table": [{"shape": "box", "sx": 1.6, "sy": 0.1, "sz": 0.9,
               "at": [0, 0.8, 0]},
              {"shape": "box", "sx": 0.1, "sy": 0.8, "sz": 0.1,
               "at": [-0.7, 0.4, -0.35]},
              {"shape": "box", "sx": 0.1, "sy": 0.8, "sz": 0.1,
               "at": [0.7, 0.4, -0.35]},
              {"shape": "box", "sx": 0.1, "sy": 0.8, "sz": 0.1,
               "at": [-0.7, 0.4, 0.35]},
              {"shape": "box", "sx": 0.1, "sy": 0.8, "sz": 0.1,
               "at": [0.7, 0.4, 0.35]}],
}


def spec_from_text(description: str, ask=None) -> dict:
    """Turn a description into a primitive-graph spec. `ask(prompt)->str`
    can supply an LLM; otherwise a keyword heuristic is used."""
    d = (description or "").lower()
    if ask:
        try:
            out = ask(
                "Convert this into JSON {\"name\":..,\"parts\":[{\"shape\":"
                "one of box,sphere,cylinder,cone,torus,pyramid,\"at\":[x,y,z]"
                ",\"scale\":..,\"r\":..,\"h\":..,\"sx\":..,\"sy\":..,\"sz\":..}]}"
                f" for: {description}. Output ONLY JSON.")
            m = __import__("re").search(r"\{.*\}", out or "", __import__("re").S)
            if m:
                spec = json.loads(m.group(0))
                if spec.get("parts"):
                    return spec
        except Exception:
            pass
    for k, parts in HEURISTIC_PARTS.items():
        if k in d:
            return {"name": k, "parts": parts}
    return {"name": "model", "parts": [{"shape": "torus",
                                        "R": 0.7, "r": 0.25}]}


# ---------------------------------------------------------------- exporters
def write_obj(mesh: Mesh, path: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Coal 3D — {mesh.name}\n")
        for (x, y, z) in mesh.verts:
            f.write(f"v {x:.5f} {y:.5f} {z:.5f}\n")
        for fc in mesh.faces:
            f.write("f " + " ".join(str(i + 1) for i in fc) + "\n")
    return path


def write_stl(mesh: Mesh, path: str) -> str:
    def tri(a, b, c):
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0])
        L = math.sqrt(sum(t * t for t in n)) or 1.0
        return tuple(t / L for t in n)
    tris = []
    for fc in mesh.faces:
        for i in range(1, len(fc) - 1):
            tris.append((mesh.verts[fc[0]], mesh.verts[fc[i]],
                         mesh.verts[fc[i + 1]]))
    with open(path, "wb") as f:
        f.write(b"Coal 3D STL".ljust(80, b"\x00"))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            n = tri(a, b, c)
            f.write(struct.pack("<12fH", *(n + a + b + c), 0))
    return path


def write_gltf(mesh: Mesh, path: str) -> str:
    """Minimal glTF 2.0 (embedded buffer) for engines/web viewers."""
    import base64
    pos = b"".join(struct.pack("<3f", *v) for v in mesh.verts)
    idx = []
    for fc in mesh.faces:
        for i in range(1, len(fc) - 1):
            idx += [fc[0], fc[i], fc[i + 1]]
    ind = b"".join(struct.pack("<I", i) for i in idx)
    buf = pos + ind
    g = {"asset": {"version": "2.0", "generator": "Coal 3D"},
         "scene": 0, "scenes": [{"nodes": [0]}],
         "nodes": [{"mesh": 0, "name": mesh.name}],
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0},
                                     "indices": 1, "mode": 4}]}],
         "buffers": [{"byteLength": len(buf), "uri":
                      "data:application/octet-stream;base64,"
                      + base64.b64encode(buf).decode()}],
         "bufferViews": [
             {"buffer": 0, "byteOffset": 0, "byteLength": len(pos),
              "target": 34962},
             {"buffer": 0, "byteOffset": len(pos), "byteLength": len(ind),
              "target": 34963}],
         "accessors": [
             {"bufferView": 0, "componentType": 5126, "count":
              len(mesh.verts), "type": "VEC3",
              "min": list(mesh.bounds()[:3]),
              "max": list(mesh.bounds()[3:])},
             {"bufferView": 1, "componentType": 5125, "count": len(idx),
              "type": "SCALAR"}]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(g, f)
    return path


def load_obj(path: str) -> Mesh:
    verts, faces = [], []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    idx.append(int(tok.split("/")[0]) - 1)
                if len(idx) >= 3:
                    faces.append(tuple(idx))
    return Mesh(verts, faces, os.path.splitext(os.path.basename(path))[0])


# ---------------------------------------------------------------- convert
def to_trimesh(mesh: Mesh, process: bool = True):
    import numpy as np
    import trimesh
    tris = []
    for f in mesh.faces:
        for i in range(1, len(f) - 1):
            tris.append([f[0], f[i], f[i + 1]])
    return trimesh.Trimesh(vertices=np.array(mesh.verts, float),
                           faces=np.array(tris, int), process=process)


def export_formats(mesh: Mesh, base: str, formats: list) -> dict:
    """Export a mesh to many formats via trimesh (obj/stl/ply/glb/gltf/off/
    3mf/dae/...). Extensions trimesh can't write are reported per-format."""
    tm = to_trimesh(mesh)
    outs = {}
    for fmt in formats:
        ext = str(fmt).lstrip(".").lower()
        p = f"{base}.{ext}"
        try:
            data = tm.export(file_type=ext)
            mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
            with open(p, mode) as f:
                f.write(data)
            outs[ext] = p
        except Exception as e:
            outs[ext] = f"error: {e}"
    return outs


def load_any(path: str):
    """Load any mesh format trimesh understands; returns trimesh mesh."""
    import trimesh
    obj = trimesh.load(path, force="mesh")
    return obj


def blender_to_obj(path: str) -> str | None:
    """Use Blender to import a format trimesh can't read (fbx/usdz/dae) and
    write it as .obj. Returns the obj path or None."""
    import tempfile
    out_base = os.path.join(tempfile.mkdtemp(prefix="rox3d-imp-"), "imported")
    outs = blender_export(path, out_base, ["obj"])
    p = outs.get("obj", "")
    return p if p and os.path.exists(p) else None


def load_mesh_any(path: str):
    """Load any mesh (trimesh first, Blender fallback for fbx/usd/dae)."""
    import trimesh
    try:
        return trimesh.load(path, force="mesh")
    except Exception:
        obj = blender_to_obj(path)
        if not obj:
            raise
        return trimesh.load(obj, force="mesh")


BLENDER_ONLY = {"fbx", "usd", "usda", "usdc", "usdz"}


def blender_path():
    import glob
    import shutil
    p = shutil.which("blender")
    if p:
        return p
    for pat in (r"C:\Program Files\Blender Foundation\Blender*\blender.exe",
                r"C:\Program Files\Blender Foundation\Blender\blender.exe"):
        hits = glob.glob(pat)
        if hits:
            return sorted(hits)[-1]
    return None


_BLENDER_SCRIPT = r'''
import bpy, sys, traceback
a = sys.argv[sys.argv.index("--") + 1:]
inp, base, fmts = a[0], a[1], a[2].split(",")
bpy.ops.wm.read_factory_settings(use_empty=True)
for m in ("io_scene_usd", "io_scene_fbx", "io_scene_gltf2"):
    try: bpy.ops.preferences.addon_enable(module=m)
    except Exception: pass
e = inp.lower()
if e.endswith(".obj"): bpy.ops.wm.obj_import(filepath=inp)
elif e.endswith((".glb", ".gltf")): bpy.ops.import_scene.gltf(filepath=inp)
elif e.endswith(".stl"): bpy.ops.wm.stl_import(filepath=inp)
elif e.endswith(".ply"): bpy.ops.wm.ply_import(filepath=inp)
elif e.endswith(".fbx"): bpy.ops.import_scene.fbx(filepath=inp)
elif e.endswith((".usd", ".usda", ".usdc", ".usdz")): bpy.ops.wm.usd_import(filepath=inp)
elif e.endswith(".dae"): bpy.ops.wm.collada_import(filepath=inp)
else: bpy.ops.wm.obj_import(filepath=inp)
for f in fmts:
    f = f.strip().lower()
    out = base + "." + f
    try:
        if f == "fbx": bpy.ops.export_scene.fbx(filepath=out)
        elif f in ("usd", "usda", "usdc", "usdz"): bpy.ops.wm.usd_export(filepath=out)
        elif f == "dae": bpy.ops.wm.collada_export(filepath=out)
        elif f == "glb": bpy.ops.export_scene.gltf(filepath=out, export_format="GLB")
        elif f == "obj": bpy.ops.wm.obj_export(filepath=out)
        elif f == "stl": bpy.ops.wm.stl_export(filepath=out)
        print("ROX3D_OK", f, out)
    except Exception as ex:
        print("ROX3D_ERR", f, repr(ex))
        traceback.print_exc()
'''


def blender_export(in_path: str, base: str, formats: list,
                   timeout: int = 600) -> dict:
    """Use Blender headless to export formats trimesh can't (fbx/usdz/...)."""
    import subprocess
    import tempfile
    bl = blender_path()
    if not bl:
        return {f: "error: blender not installed" for f in formats}
    script = os.path.join(tempfile.gettempdir(), "rox3d_blender.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(_BLENDER_SCRIPT)
    args = [bl, "--background", "--factory-startup", "--python", script,
            "--", in_path, base, ",".join(formats)]
    outs = {}
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=0x08000000)
        log = (r.stdout or "") + (r.stderr or "")
        for f in formats:
            p = f"{base}.{f.lower()}"
            if os.path.exists(p):
                outs[f] = p
            else:
                err = next((ln for ln in log.splitlines()
                            if ln.startswith("ROX3D_ERR") and
                            f.lower() in ln.lower()), "")
                outs[f] = "error: " + (err or (
                    log.strip().splitlines()[-1][:120] if log.strip()
                    else "blender failed"))
    except Exception as e:
        for f in formats:
            outs[f] = f"error: {str(e)[:80]}"
    return outs


def export_mesh(mesh: Mesh, base: str, formats: list) -> dict:
    """Export to any formats: trimesh for common, Blender for fbx/usdz/..."""
    common = [f for f in formats if f.lstrip(".").lower() not in BLENDER_ONLY]
    special = [f for f in formats if f.lstrip(".").lower() in BLENDER_ONLY]
    outs = export_formats(mesh, base, common) if common else {}
    if special:
        obj_path = base + ".obj"
        if not os.path.exists(obj_path):
            write_obj(mesh, obj_path)
        outs.update(blender_export(obj_path, base,
                                   [f.lstrip(".") for f in special]))
    return outs


def validate(path_or_mesh) -> dict:
    import numpy as np
    import trimesh
    if isinstance(path_or_mesh, str):
        m = load_mesh_any(path_or_mesh)
    else:
        m = to_trimesh(path_or_mesh)
    b = m.bounds
    return {
        "vertices": int(len(m.vertices)),
        "faces": int(len(m.faces)),
        "watertight": bool(m.is_watertight),
        "winding_consistent": bool(m.is_winding_consistent),
        "euler_number": int(m.euler_number),
        "volume": (round(float(m.volume), 6) if m.is_watertight else None),
        "components": int(m.body_count),
        "bounds_min": [round(float(x), 4) for x in (b[0] if b is not None
                                                    else (0, 0, 0))],
        "bounds_max": [round(float(x), 4) for x in (b[1] if b is not None
                                                    else (0, 0, 0))],
        "is_empty": bool(m.is_empty),
    }


def repair(mesh: Mesh) -> Mesh:
    """Basic repair: merge duplicate vertices, fix winding, fill holes."""
    import trimesh
    m = to_trimesh(mesh)
    try:
        m.merge_vertices()
    except Exception:
        pass
    try:
        m.fix_normals()
    except Exception:
        pass
    try:
        m.fill_holes()
    except Exception:
        pass
    return Mesh([tuple(v) for v in m.vertices.tolist()],
                [tuple(int(i) for i in f) for f in m.faces.tolist()],
                mesh.name)


# ---------------------------------------------------------------- preview
def render_png(mesh: Mesh, path: str, w=480, h=360, bg=(18, 26, 40)):
    """Flat-shaded painter's-algorithm preview using Pillow."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), bg)
    dr = ImageDraw.Draw(img)
    if not mesh.verts or not mesh.faces:
        img.save(path)
        return path
    x0, y0, z0, x1, y1, z1 = mesh.bounds()
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    span = max(x1 - x0, y1 - y0, z1 - z0) or 1.0
    dist = span * 2.4
    scale = min(w, h) * dist / (span * 2.2)
    light = (0.4, 0.9, 0.35)
    tris = []
    for fc in mesh.faces:
        for i in range(1, len(fc) - 1):
            a, b, c = mesh.verts[fc[0]], mesh.verts[fc[i]], mesh.verts[fc[i + 1]]
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
                 u[0] * v[1] - u[1] * v[0])
            L = math.sqrt(sum(t * t for t in n)) or 1.0
            n = tuple(t / L for t in n)
            lam = abs(n[0] * light[0] + n[1] * light[1] + n[2] * light[2])
            shade = 0.25 + 0.75 * min(1.0, lam)
            pts, ok = [], True
            for (px, py, pz) in (a, b, c):
                X, Y, Z = px - cx, py - cy, pz - cz + dist
                if Z <= 0.001:
                    ok = False
                    break
                pts.append((w / 2 + (X / Z) * scale,
                            h / 2 - (Y / Z) * scale))
            if not ok:
                continue
            depth = (a[2] + b[2] + c[2]) / 3 - cz
            col = (int(60 * shade + 30), int(130 * shade + 40),
                   int(210 * shade + 30))
            tris.append((depth, pts, col))
    tris.sort(key=lambda t: t[0])
    for _d, pts, col in tris:
        dr.polygon(pts, fill=col, outline=(int(col[0] * .7),
                                           int(col[1] * .7),
                                           int(col[2] * .7)))
    img.save(path)
    return path


def render_textured_png(mesh, uvs, albedo_path, path, w=480, h=560,
                        bg=(18, 26, 40)):
    """Flat-shaded preview that samples the albedo at each face's UV
    centroid, so the texture is actually visible on the model."""
    import numpy as np
    from PIL import Image, ImageDraw
    try:
        tex = np.asarray(Image.open(albedo_path).convert("RGB"))
        th_, tw_ = tex.shape[:2]
    except Exception:
        tex = None
    img = Image.new("RGB", (w, h), bg)
    dr = ImageDraw.Draw(img)
    if not mesh.verts or not mesh.faces:
        img.save(path)
        return path
    x0, y0, z0, x1, y1, z1 = mesh.bounds()
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    span = max(x1 - x0, y1 - y0, z1 - z0) or 1.0
    dist = span * 2.4
    scale = min(w, h) * dist / (span * 2.2)
    light = (0.4, 0.9, 0.35)
    tris = []
    for fc in mesh.faces:
        for i in range(1, len(fc) - 1):
            idx = (fc[0], fc[i], fc[i + 1])
            a, b, c = (mesh.verts[idx[0]], mesh.verts[idx[1]],
                       mesh.verts[idx[2]])
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
                 u[0] * v[1] - u[1] * v[0])
            L = math.sqrt(sum(t * t for t in n)) or 1.0
            n = tuple(t / L for t in n)
            lam = abs(n[0] * light[0] + n[1] * light[1] + n[2] * light[2])
            shade = 0.35 + 0.65 * min(1.0, lam)
            pts, ok = [], True
            for (px, py, pz) in (a, b, c):
                X, Y, Z = px - cx, py - cy, pz - cz + dist
                if Z <= 0.001:
                    ok = False
                    break
                pts.append((w / 2 + (X / Z) * scale,
                            h / 2 - (Y / Z) * scale))
            if not ok:
                continue
            if tex is not None:
                us = [uvs[k] for k in idx]
                uu = sum(p[0] for p in us) / 3.0
                vv = sum(p[1] for p in us) / 3.0
                px = int(min(max(uu, 0.0), 0.999) * tw_)
                py = int(min(max(vv, 0.0), 0.999) * th_)
                col = tuple(int(min(255, ch * shade)) for ch in tex[py, px])
            else:
                col = (int(60 * shade + 30), int(130 * shade + 40),
                       int(210 * shade + 30))
            depth = (a[2] + b[2] + c[2]) / 3 - cz
            tris.append((depth, pts, col))
    tris.sort(key=lambda t: t[0])
    for _d, pts, col in tris:
        dr.polygon(pts, fill=col, outline=(int(col[0] * .85),
                                           int(col[1] * .85),
                                           int(col[2] * .85)))
    img.save(path)
    return path


# ---------------------------------------------------------------- orchestrate
def generate(outdir: str, shape: str | None = None, description: str = "",
             spec: dict | None = None, name: str | None = None,
             size: float | None = None, ask=None, formats=None,
             **kwargs) -> dict:
    os.makedirs(outdir, exist_ok=True)
    if spec is None and (description or "").strip() and not shape:
        spec = spec_from_text(description, ask=ask)
    if spec is not None:
        mesh = build_from_spec(spec)
        nm = name or spec.get("name") or "model"
    else:
        mesh = make(shape or "torus", **kwargs)
        nm = name or mesh.name
    if size:
        x0, y0, z0, x1, y1, z1 = mesh.bounds()
        m = max(x1 - x0, y1 - y0, z1 - z0) or 1.0
        mesh.scaled(float(size) / m)
    ts = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.join(outdir, f"{nm}-{ts}")
    outs = {
        "obj": write_obj(mesh, base + ".obj"),
        "stl": write_stl(mesh, base + ".stl"),
        "gltf": write_gltf(mesh, base + ".gltf"),
        "png": render_png(mesh, base + ".png"),
    }
    if formats:
        for k, v in export_mesh(mesh, base, list(formats)).items():
            outs[k] = v
    return {"files": outs, "stats": mesh.stats(), "spec": spec,
            "shape": shape, "description": description}