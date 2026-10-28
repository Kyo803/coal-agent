"""Verify the whole ROX N toolchain in one command.

    python verify_toolchain.py
    python verify_toolchain.py --json

Checks: host compilers (iverilog/vvp/gtkwave/blender/node/git),
the WSL sandbox + its Verilog toolchain, the ROX-Compute accelerator,
and the 3D / texturing Python deps.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def check_host():
    try:
        import toolchain
        return toolchain.report()
    except Exception as e:
        return {"error": str(e)[:200]}


def check_wsl():
    try:
        r = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True,
                           text=True, timeout=25)
        distros = [d.strip() for d in
                   (r.stdout or "").replace("\x00", "").splitlines()
                   if d.strip()]
        info = {"installed": True, "distros": distros}
        if distros:
            d = distros[0]
            v = subprocess.run(
                ["wsl.exe", "-d", d, "-u", "root", "--", "bash", "-lc",
                 "iverilog -V | head -n1; verilator --version 2>/dev/null"],
                capture_output=True, text=True, timeout=90)
            info["toolchain"] = (v.stdout or v.stderr).strip()[:300]
        return info
    except Exception as e:
        return {"installed": False, "hint":
                "run setup_wsl.ps1 (needs an admin prompt)", "error":
                str(e)[:160]}


def check_accel():
    try:
        import roxcompute
        return {"available": roxcompute.available(),
                "probe": roxcompute.probe()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def check_3d():
    mods = {}
    for m in ("numpy", "PIL", "trimesh", "xatlas", "scipy"):
        try:
            __import__(m)
            mods[m] = True
        except Exception:
            mods[m] = False
    try:
        import threed
        mods["blender"] = threed.blender_path()
    except Exception:
        mods["blender"] = None
    return mods


def main():
    report = {"host": check_host(), "wsl": check_wsl(),
              "accelerator": check_accel(), "python_3d": check_3d()}
    if "--json" in sys.argv:
        print(json.dumps(report, indent=1))
    else:
        h = report["host"]
        print("HOST TOOLCHAIN")
        for k, v in h.items():
            print(f"  {k:10s} {v}")
        w = report["wsl"]
        print("WSL SANDBOX")
        print(f"  installed  {w.get('installed')}")
        if w.get("distros"):
            print(f"  distros    {', '.join(w['distros'])}")
        if w.get("toolchain"):
            print(f"  toolchain  {w['toolchain'].splitlines()}")
        if w.get("hint"):
            print(f"  hint       {w['hint']}")
        a = report["accelerator"].get("probe", {})
        print("ACCELERATOR (ROX-Compute)")
        print(f"  providers  {a.get('providers')}")
        p3 = report["python_3d"]
        print("PYTHON 3D DEPS")
        for k, v in p3.items():
            print(f"  {k:10s} {v}")
    ok = bool(report["host"].get("iverilog"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
