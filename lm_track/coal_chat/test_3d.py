"""Tests for the 3D generation engine + tool registration."""
import os
import tempfile

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
    import threed
    from tools import specs

    print("== 1. primitives ==")
    for s in sorted(threed.SHAPES):
        m = threed.make(s)
        ok(f"{s} builds", len(m.verts) > 0 and len(m.faces) > 0)

    print("== 2. generate pipeline ==")
    d = tempfile.mkdtemp()
    res = threed.generate(d, shape="torus", R=1.0, r=0.3, size=2.0)
    for k in ("obj", "stl", "gltf", "png"):
        p = res["files"][k]
        ok(f"{k} non-empty", os.path.exists(p) and os.path.getsize(p) > 0)

    print("== 3. description spec ==")
    res2 = threed.generate(d, description="a low poly rocket")
    ok("description built", res2["stats"]["faces"] > 0)
    ok("spec recorded", isinstance(res2["spec"], dict)
       and res2["spec"].get("parts"))

    print("== 4. obj round-trip ==")
    m = threed.load_obj(res["files"]["obj"])
    ok("reloaded verts", len(m.verts) == res["stats"]["vertices"])
    ok("render ok", threed.render_png(m, os.path.join(d, "re.png")) and
       os.path.getsize(os.path.join(d, "re.png")) > 0)

    print("== 5. registry ==")
    names = [s["name"] for s in specs.by_category("3d")]
    ok("3d category registered",
       {"generate_3d", "render_3d", "list_3d_shapes", "convert_3d",
        "validate_3d", "repair_3d"} <= set(names))

    print("== 6. extra formats ==")
    res3 = threed.generate(d, shape="torus", R=1.0, r=0.3,
                           formats=["glb", "ply", "off", "3mf", "stl"])
    ok("glb exported", os.path.exists(res3["files"].get("glb", ""))
       and os.path.getsize(res3["files"]["glb"]) > 0)
    ok("ply exported", os.path.exists(res3["files"].get("ply", "")))
    ok("3mf exported", os.path.exists(res3["files"].get("3mf", "")))

    print("== 7. convert + validate ==")
    from tools.handlers_3d import convert_3d, validate_3d, repair_3d

    class _Ctx:
        workspace = d
    c = convert_3d({"path": res["files"]["obj"], "formats": ["glb", "stl",
                                                             "ply"]}, _Ctx())
    ok("convert ok", c["ok"] and "glb" in c["output"])
    v = validate_3d({"path": res["files"]["obj"]}, _Ctx())
    ok("validate ok", v["ok"] and "vertices" in v["output"])
    rp = repair_3d({"path": res["files"]["obj"],
                    "formats": ["obj", "stl"]}, _Ctx())
    ok("repair ok", rp["ok"] and "repaired" in rp["output"])

    print("== 8. pro formats (Blender: fbx/usdz/dae) ==")
    extra = threed.export_mesh(m, os.path.join(d, "pro"), ["fbx", "usdz", "dae"])
    for fmt in ("fbx", "usdz", "dae"):
        p = extra.get(fmt, "")
        ok(f"{fmt} exported", os.path.exists(p) and os.path.getsize(p) > 0)

    print("== 9. mesh validation metrics ==")
    vt = threed.validate(os.path.join(d, "pro.fbx"))
    ok("fbx validates", vt["vertices"] > 0 and vt["faces"] > 0)
    ok("bounds present", len(vt["bounds_min"]) == 3
       and vt["bounds_max"][0] > vt["bounds_min"][0])

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
