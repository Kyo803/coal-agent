"""Build and verify a chip from the command line.

    py -3.15 build.py "UART loopback"
    py -3.15 build.py "8-bit counter" --name demo_counter

This is the model-free path: `chipflow.build` picks the deterministic
generator (or composition) from the description and runs the full gate.
"""
import argparse
import os
import sys

import chipflow


def main() -> int:
    ap = argparse.ArgumentParser(description="Build and verify a chip.")
    ap.add_argument("spec", nargs="+", help="what the chip should do")
    ap.add_argument("--name", default="cli_build", help="work directory name")
    ap.add_argument("--kind", default=None, help="force a block kind")
    ap.add_argument("--views", action="store_true",
                    help="also render block/schematic/die/3D views")
    a = ap.parse_args()
    spec = " ".join(a.spec)
    print(f"building: {spec}")
    rep = chipflow.build(a.name, spec=spec, kind=a.kind,
                         make_views=a.views)
    print(chipflow.summary_text(rep))
    print(f"source: {rep.get('source')}")
    print(f"report: {rep.get('path')}")
    d = os.path.dirname(rep.get("path") or "")
    if d:
        print(f"dir   : {d}")
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
