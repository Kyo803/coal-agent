"""2D floorplan from real nextpnr placement.

Every used cell is drawn at its actual BEL site (X/Y from nextpnr), grouped
into module regions ("cores"). A flat design shows one core; a composition
(e.g. UART = tx + rx + ctl) shows one region per submodule.

The drawing zooms to the placed region so cells stay readable; the axis
labels and the subtitle say which window of the fabric is shown.
"""
from __future__ import annotations

import json
import os
import re

# iCE40 fabric dimensions (LC columns x rows).
_FABRIC = {"hx8k": (160, 48), "up5k": (120, 44), "lp384": (24, 16)}

_GREYS = ["#f2f2f2", "#d0d0d0", "#a8a8a8", "#8a8a8a", "#6f6f6f",
          "#565656", "#3f3f3f", "#2c2c2c"]


def _bel_xy(attrs: dict):
    bel = (attrs or {}).get("NEXTPNR_BEL") or ""
    m = re.match(r"X(\d+)/Y(\d+)/(\w+)", str(bel))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), m.group(3)


def _group_of(cell: str) -> str:
    name = cell.lstrip("$")
    if "." in name:
        head = name.split(".", 1)[0]
        head = head.split("_SB_")[0].split("_LC")[0]
        if head:
            return head
    return "core"


def _find_placed(d: str, top: str) -> str | None:
    for f in (f"_{top}_placed.json", f"_{top}_ice40.json",
              f"_{top}_pnr.json", "place.asc"):
        p = os.path.join(d, f)
        if not os.path.exists(p):
            continue
        try:
            if "NEXTPNR_BEL" in open(p, encoding="utf-8",
                                     errors="ignore").read(4000000):
                return p
        except Exception:
            continue
    return None


def _stats(d: str):
    for f in sorted(os.listdir(d)):
        if f.endswith("-report.json"):
            try:
                rep = json.load(open(os.path.join(d, f), encoding="utf-8"))
            except Exception:
                continue
            area = rep.get("area") or {}
            pnr = rep.get("pnr") or {}
            return {"device": pnr.get("device"),
                    "fmax": area.get("fmax_mhz"),
                    "lc_used": area.get("lc"),
                    "cells": area.get("cells"),
                    "ffs": area.get("ffs")}
    return {}


def render_from_dir(d: str, top: str, out_png: str | None = None) -> dict:
    d = os.path.abspath(d)
    placed = _find_placed(d, top)
    if not placed:
        return {"ok": False,
                "output": f"no placement data in {d} (run chip_gate/chip_build)"}
    out_png = out_png or os.path.join(d, f"{top}-floorplan.png")
    st = _stats(d)
    try:
        info = render(placed, out_png, top, **st)
    except Exception as e:
        return {"ok": False, "output": f"floorplan render failed: {e}"}
    return {"ok": True, "png": out_png, "info": info,
            "output": (f"floorplan for {top}:\n"
                       f"  png      : {out_png}\n"
                       f"  cores    : {info['cores']}\n"
                       f"  cells    : {info['cells']} placed\n"
                       f"  window   : X{info['window'][0]}..{info['window'][2]}"
                       f" Y{info['window'][1]}..{info['window'][3]}\n"
                       f"  device   : {info['device']} "
                       f"({info['cols']}x{info['rows']} LC fabric)")}


def render(placed_json: str, out_png: str, top: str, device=None,
           fmax=None, lc_used=None, cells=None, ffs=None, **_) -> dict:
    from PIL import Image, ImageDraw

    try:
        from .views import _font
        font, small = _font(14), _font(11)
    except Exception:                       # pragma: no cover
        from PIL import ImageFont
        font = small = ImageFont.load_default()

    try:
        data = json.load(open(placed_json, encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"cannot read {placed_json}: {e}")

    mod = None
    for m in (data.get("modules") or {}).values():
        mod = m
        break
    if not mod:
        raise ValueError("no module in placement JSON")

    pts = {}
    for name, c in (mod.get("cells") or {}).items():
        xy = _bel_xy(c.get("attributes") or {})
        if xy:
            x, y, bel = xy
            if bel.startswith("io"):
                continue                     # keep the drawing about logic
            pts[name] = (x, y)
    if not pts:
        raise ValueError("no placed logic cells")

    dev = (device or "hx8k").lower()
    full_cols, full_rows = _FABRIC.get(dev, (160, 48))
    full_cols = max(full_cols, max(x for x, _ in pts.values()) + 1)
    full_rows = max(full_rows, max(y for _, y in pts.values()) + 1)

    # window around the placed cells, clamped to the fabric
    margin = 3
    x0 = max(0, min(x for x, _ in pts.values()) - margin)
    y0 = max(0, min(y for _, y in pts.values()) - margin)
    x1 = min(full_cols - 1, max(x for x, _ in pts.values()) + margin)
    y1 = min(full_rows - 1, max(y for _, y in pts.values()) + margin)
    cols, rows = x1 - x0 + 1, y1 - y0 + 1

    groups = {}
    for name, xy in pts.items():
        groups.setdefault(_group_of(name), []).append(xy)
    order = sorted(groups, key=lambda g: (-len(groups[g]), g))
    colour = {g: _GREYS[i % len(_GREYS)] for i, g in enumerate(order)}

    pad, top_h, axis = 22, 54, 18
    legend_cols = 4
    legend_rows = max(1, (min(len(order), 8) + legend_cols - 1)
                      // legend_cols)
    legend_h = 26 + 20 * legend_rows
    cell = max(6, min(30, 900 // max(cols, 1)))
    w = pad * 2 + axis + cols * cell + 60
    h = top_h + axis + rows * cell + legend_h + 30
    img = Image.new("RGB", (w, h), "#0b0b0b")
    dr = ImageDraw.Draw(img)

    dr.text((pad, 12), f"{top} · 2D floorplan (nextpnr placement)",
            fill="#f2f2f2", font=font)
    lc_avail = full_cols * full_rows
    sub = []
    if lc_used is not None:
        sub.append(f"LC {lc_used}/{lc_avail}")
    if cells:
        sub.append(f"{cells} cells")
    if ffs:
        sub.append(f"{ffs} FFs")
    if fmax:
        sub.append(f"Fmax {fmax} MHz")
    sub.append(f"{dev} · {full_cols}x{full_rows} fabric")
    dr.text((pad, 32), "  ·  ".join(sub), fill="#8a8a8a", font=small)

    gx, gy = pad + axis, top_h + axis
    dr.rectangle([gx, gy, gx + cols * cell, gy + rows * cell],
                 outline="#2a2a2a")
    for x in range(0, cols + 1, 5):
        dr.line([(gx + x * cell, gy), (gx + x * cell, gy + rows * cell)],
                fill="#161616")
        dr.text((gx + x * cell - 6, gy + rows * cell + 4), str(x0 + x),
                fill="#5f5f5f", font=small)
    for y in range(0, rows + 1, 5):
        dr.line([(gx, gy + y * cell), (gx + cols * cell, gy + y * cell)],
                fill="#161616")
        dr.text((pad, gy + y * cell - 5), str(y0 + y), fill="#5f5f5f",
                font=small)
    dr.text((gx + cols * cell // 2 - 30, gy + rows * cell + 22), "X →",
            fill="#5f5f5f", font=small)
    dr.text((pad - 4, gy - 16), "Y ↑", fill="#5f5f5f", font=small)

    # core regions (bounding box per module)
    for g in order:
        xs = [p[0] for p in groups[g]]
        ys = [p[1] for p in groups[g]]
        bx0, by0 = min(xs), min(ys)
        bx1, by1 = max(xs), max(ys)
        m = 1
        dr.rectangle(
            [gx + (bx0 - x0 - m) * cell + 1, gy + (by0 - y0 - m) * cell + 1,
             gx + (bx1 - x0 + m + 1) * cell - 1,
             gy + (by1 - y0 + m + 1) * cell - 1],
            outline="#e8e8e8")
        if len(order) > 1 and g in order[:3]:
            label = f"{g} ({len(groups[g])})"
            lx = gx + (bx0 - x0) * cell + 3
            ly2 = gy + (by0 - y0) * cell + 2
            tw = len(label) * 6 + 4
            dr.rectangle([lx - 2, ly2 - 1, lx + tw, ly2 + 13],
                         fill="#0b0b0b")
            dr.text((lx, ly2), label, fill="#e8e8e8", font=small)

    for g in order:
        for (x, y) in groups[g]:
            cx = gx + (x - x0) * cell
            cy = gy + (y - y0) * cell
            dr.rectangle([cx + 1, cy + 1, cx + cell - 1, cy + cell - 1],
                         fill=colour[g])

    ly = gy + rows * cell + 44
    for i, g in enumerate(order[:8]):
        cx = pad + (i % legend_cols) * 200
        cy = ly + (i // legend_cols) * 20
        dr.rectangle([cx, cy, cx + 10, cy + 10], fill=colour[g])
        dr.text((cx + 16, cy - 2), f"{g}  ({len(groups[g])} cells)",
                fill="#c9c9c9", font=small)
    if len(order) > 8:
        dr.text((pad, ly + 20 * legend_rows),
                f"+{len(order) - 8} more regions", fill="#6f6f6f",
                font=small)

    img.save(out_png)
    return {"png": out_png, "cells": len(pts), "cores": order,
            "device": dev, "cols": full_cols, "rows": full_rows,
            "window": [x0, y0, x1, y1],
            "groups": {g: len(groups[g]) for g in order}}
