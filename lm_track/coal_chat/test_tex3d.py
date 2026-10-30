"""Tests for the Coal texturing engine + image->3D."""
import os
import tempfile

import numpy as np

PASS = FAIL = 0


def ok(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")


def main():
    import img3d
    import tex3d
    import threed
    from tools import specs

    d = tempfile.mkdtemp()

    print("== 1. uv unwrap ==")
    m = threed.make("torus", R=1.0, r=0.3)
    uw = tex3d.unwrap(m, res=512)
    ok("unwrap produced uvs", uw["uvs"].shape[1] == 2
       and len(uw["vertices"]) == len(uw["uvs"]))
    ok("uvs in 0..1", float(uw["uvs"].min()) >= -0.01
       and float(uw["uvs"].max()) <= 1.01)
    ok("faces triangulated", uw["faces"].shape[1] == 3)
    box = threed.make("box")
    ubox = tex3d.unwrap(box, res=256)
    ok("quads triangulated", ubox["faces"].shape[1] == 3
       and len(ubox["faces"]) == 12)

    print("== 2. tiling ==")
    tl = tex3d.plan_tiles(512, 256, 64)
    ok("tiles cover area", len(tl) >= 9)
    ok("last tile reaches edge", tl[-1][2] == 512 and tl[-1][3] == 512)

    print("== 3. seamless stitch ==")
    res = 512
    full = tex3d.gen_procedural((0, 0, res, res),
                                {"style": "rock", "seed": 3, "freq": 5.0,
                                 "grain": 8.0, "octaves": 7}, res)
    stitched, rects = tex3d.synthesize(res, tile=192, overlap=64,
                                       backend="procedural", style="rock",
                                       seed=3)
    diff = float(np.abs(stitched.astype(float) - full.astype(float)).mean())
    ok(f"tiles blend seamlessly (mean diff {diff:.2f})", diff < 3.0)

    print("== 4. detail + super-res ==")
    sharp = tex3d.unsharp(full, amount=1.0, radius=2.0)
    ok("unsharp keeps shape", sharp.shape == full.shape)
    det = tex3d.add_detail(full, amount=0.3, seed=1)
    ok("detail adds high-freq", float(np.abs(det.astype(float) -
       full.astype(float)).mean()) > 0.5)
    up = tex3d.super_res(full, 2)
    ok("super_res doubles size", up.shape[0] == res * 2)

    print("== 5. bakes ==")
    maps = tex3d.bake_maps(uw["uvs"], uw["faces"], 256, uw["vertices"],
                           uw["faces"], do_ao=True, ao_samples=6)
    ok("curvature baked", maps["curvature"].shape == (256, 256)
       and maps["curvature"].max() > 0)
    ok("normal baked", maps["normal"].shape[-1] == 3)
    ok("roughness baked", maps["roughness"].shape == (256, 256))
    ok("ao baked", "ao" in maps and maps["ao"].max() > 0)

    print("== 6. texture + apply ==")
    res2 = tex3d.texture_mesh(m, d, name="vase", resolution=512, tile=256,
                              overlap=64, style="hull", ao_samples=6,
                              formats=("glb", "obj", "fbx"))
    for k in ("albedo", "glb", "obj", "fbx", "normal", "roughness"):
        p = res2["files"].get(k, "")
        ok(f"{k} exported", os.path.exists(p) and os.path.getsize(p) > 0)
    ok("tiles counted", res2["stats"]["tiles"] >= 9)

    print("== 7. parts ==")
    two = threed.Mesh()
    two.add(threed.make("box"), (0, 0, 0))
    two.add(threed.make("box"), (5, 0, 0))
    parts = tex3d.split_parts(two)
    ok("split into parts", len(parts) == 2)
    pr = tex3d.texture_parts(two, d, resolution=256, tile=128,
                             formats=("glb",))
    ok("textured parts", pr["parts"] == 2 and all(
        r["files"].get("glb") for r in pr["results"]))

    print("== 8. image -> 3d ==")
    from PIL import Image
    n = 128
    yy, xx = np.mgrid[0:n, 0:n]
    dist = np.sqrt((xx - n / 2) ** 2 + (yy - n / 2) ** 2)
    img = np.zeros((n, n, 3), np.uint8)
    img[..., :] = (30, 40, 60)
    ball = dist < n * 0.35
    img[..., 0] = np.where(ball, 240 - dist * 2, img[..., 0])
    img[..., 1] = np.where(ball, 140 - dist, img[..., 1])
    img[..., 2] = np.where(ball, 60, img[..., 2])
    src = os.path.join(d, "pic.png")
    Image.fromarray(img).save(src)
    ok("auto_mask finds subject", img3d.auto_mask(img).sum() > 0)
    for method in ("relief", "silhouette"):
        r = img3d.image_to_3d(src, d, method=method, size=64)
        ok(f"{method} builds mesh", r["stats"]["faces"] > 0
           and os.path.getsize(r["files"]["obj"]) > 0)
    dep = np.asarray(Image.fromarray(
        (np.clip(img[..., 0] / 255.0, 0, 1) * 255).astype(np.uint8)))
    r = img3d.image_to_3d(src, d, method="depth", depth_map=dep, size=64)
    ok("depth method builds mesh", r["stats"]["faces"] > 0)

    print("== 9. registry ==")
    names = [s["name"] for s in specs.by_category("3d")]
    ok("new 3d tools registered",
       {"texture_3d", "image_to_3d", "list_3d_backends"} <= set(names))

    print("== 10. PBR + quilting + banded ==")
    seeds = [tex3d.gen_procedural((0, 0, 128, 128),
                                  {"style": "rock", "seed": k, "freq": 6.0,
                                   "grain": 8.0, "octaves": 7}, 128)
             for k in range(2)]
    q = tex3d.quilt_from_seeds(seeds, 512, patch=128, overlap=32, cand=8,
                               seed=1)
    ok("quilting builds image", q.shape == (512, 512, 3))
    ok("quilting is not a plain repeat",
       float(np.abs(q[64:128, 64:128].astype(float)
                    - q[320:384, 320:384].astype(float)).mean()) > 0.5)
    n_det = tex3d.normal_from_albedo(q, 0.6)
    ok("normal from albedo", n_det.shape[-1] == 3)
    n_cmb = tex3d.combine_normals(
        tex3d.height_to_normal(q[..., 0], 1.4), n_det)
    ok("combine normals", n_cmb.shape[-1] == 3)
    orm = tex3d.pack_orm(np.full((8, 8), 255, np.uint8),
                         np.full((8, 8), 128, np.uint8),
                         np.full((8, 8), 230, np.uint8))
    ok("orm packed (AO/rough/metal)", orm[0, 0, 0] == 255
       and orm[0, 0, 1] == 128 and orm[0, 0, 2] == 230)
    full = tex3d.gen_procedural((0, 0, 512, 512),
                                {"style": "rock", "seed": 3, "freq": 5.0,
                                 "grain": 8.0, "octaves": 7}, 512)
    banded, _ = tex3d.synthesize(512, tile=192, overlap=64, style="rock",
                                 seed=3, band=128)
    ok("banded stitch == full (seamless)",
       float(np.abs(banded.astype(float) - full.astype(float)).mean()) < 3.0)
    mips = tex3d.write_mipmaps(q, os.path.join(d, "mip"), levels=3)
    ok("mipmaps written", len(mips) == 3
       and all(os.path.getsize(x) > 0 for x in mips))

    print("== 11. PBR glb wiring ==")
    rp = tex3d.texture_mesh(m, d, name="pbrcheck", resolution=256, tile=128,
                            overlap=32, style="metal", ao_samples=4,
                            mipmaps=2, formats=("glb",))
    ok("orm map written", os.path.exists(rp["files"].get("orm", "")))
    ok("mipmap chain", len(rp["files"].get("mipmaps", [])) >= 1)
    import trimesh
    sc = trimesh.load(rp["files"]["glb"])
    mat = list(sc.geometry.values())[0].visual.material
    ok("glb normalTexture", getattr(mat, "normalTexture", None) is not None)
    ok("glb metalRoughTexture",
       getattr(mat, "metallicRoughnessTexture", None) is not None)

    print("== 12. AI backend contract ==")
    try:
        import coalcompute
        pm = coalcompute.pick_model()
        if pm == "procedural":
            src, info = tex3d.ai_source("test prompt", 64)
            ok("ai_source degrades gracefully without a model",
               src is None and "procedural" in str(info))
        else:
            print(f"  [info] AI model available: {pm}")
    except Exception as e:
        print("  [skip]", str(e)[:80])

    print("== 13. low-poly man + spiderman style ==")
    man = threed.man()
    ok("man builds", len(man.verts) > 0 and len(man.faces) > 0)
    ok("man is low-poly (<300 faces)", len(man.faces) < 300)
    uwm = tex3d.unwrap(man, res=256)
    ok("man unwraps (mixed quad/tri faces)", uwm["faces"].shape[1] == 3)
    web = tex3d.gen_procedural((0, 0, 256, 256),
                               {"style": "spiderman", "seed": 1,
                                "grain": 6.0, "octaves": 7}, 256)
    ok("spiderman texture builds", web.shape == (256, 256, 3))
    r_, g_, b_ = (web[..., 0].mean(), web[..., 1].mean(),
                  web[..., 2].mean())
    ok("spiderman is red-dominant", r_ > g_ and r_ > b_)
    ok("spiderman has dark web lines",
       float((web.mean(axis=2) < 40).mean()) > 0.004)

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
