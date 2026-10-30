"""2D and 3D views generated from the actual, verified design.

    2D:  block diagram (ports/hierarchy), gate schematic (yosys netlist),
         die map (area by cell type)
    3D:  die/package model exported as GLB/FBX (reuses threed)

Everything is derived from the synthesised netlist, not hand-drawn.
"""
from __future__ import annotations

import json
import os
import re

from . import core


# ------------------------------------------------------------------ helpers
def _pil():
    from PIL import Image, ImageDraw, ImageFont
    return Image, ImageDraw, ImageFont


def _font(size=14):
    _, _, ImageFont = _pil()
    try:
        return ImageFont.truetype("consola.ttf", size)
    except Exception:
        try:
            return ImageFont.load_default(size)
        except Exception:
            return ImageFont.load_default()


def parse_ports(rtl: str):
    """Extract (dir, width, name) from a module header."""
    ports = []
    hdr = rtl
    m = re.search(r"\bmodule\s+\w+\s*(#\s*\([^)]*\))?\s*\((.*?)\)\s*;",
                  rtl, re.S)
    if m:
        hdr = m.group(2)

    def w_of(txt):
        mm = re.search(r"\[\s*([^:\]]+)\s*:\s*([^\]]+)\]", txt)
        return txt.count(",") + 1 if not mm else mm.group(0).strip()

    for stmt in re.split(r",\s*(?![^\[]*\])", hdr):
        d = re.search(r"\b(input|output|inout)\b", stmt)
        if not d:
            continue
        names = re.findall(r"[A-Za-z_]\w*", stmt)
        if not names:
            continue
        name = names[-1]
        if name in ("wire", "reg", "logic", "signed", "input", "output",
                    "inout"):
            continue
        ports.append({"dir": d.group(1), "width": w_of(stmt), "name": name})
    return ports


def top_module(rtl: str) -> str | None:
    m = re.search(r"\bmodule\s+([A-Za-z_]\w*)", rtl or "")
    return m.group(1) if m else None


# ------------------------------------------------------------------ 2D block
def block_diagram(rtl_path: str, out_png: str) -> str:
    """Draw the module as a block with its ports (left=in, right=out)."""
    Image, ImageDraw, _ = _pil()
    rtl = open(rtl_path, encoding="utf-8", errors="ignore").read()
    ports = parse_ports(rtl)
    top = top_module(rtl) or "module"
    ins = [p for p in ports if p["dir"] == "input"]
    outs = [p for p in ports if p["dir"] != "input"]
    rows = max(len(ins), len(outs), 1)
    H = 70 + rows * 30 + 40
    W = 640
    img = Image.new("RGB", (W, H), (18, 22, 30))
    dr = ImageDraw.Draw(img)
    f = _font(14)
    fb = _font(18)
    bx0, bx1 = 200, 440
    by0, by1 = 50, H - 30
    dr.rounded_rectangle([bx0, by0, bx1, by1], 8, fill=(34, 42, 58),
                         outline=(120, 160, 220), width=2)
    tw = dr.textlength(top, font=fb)
    dr.text(((bx0 + bx1 - tw) / 2, by0 + 10), top, fill=(230, 236, 245),
            font=fb)
    for i, p in enumerate(ins):
        y = by0 + 46 + i * 30
        dr.line([(120, y + 6), (bx0, y + 6)], fill=(120, 200, 150), width=2)
        dr.text((124, y), f"{p['name']} {p['width']}", fill=(160, 220, 185),
                font=f)
    for i, p in enumerate(outs):
        y = by0 + 46 + i * 30
        dr.line([(bx1, y + 6), (520, y + 6)], fill=(230, 170, 120), width=2)
        dr.text((bx1 + 6, y), f"{p['name']} {p['width']}", fill=(235, 190, 150),
                font=f)
    dr.text((8, 10), "RTL block diagram", fill=(140, 150, 170), font=f)
    img.save(out_png)
    return out_png


# ------------------------------------------------------------------ 2D gate
def netlist_json(rtl_files, cwd, top, out_json, timeout=900):
    ys = core.yosys_cmd()
    if not ys:
        return None
    files = " ".join(f'"{f}"' for f in rtl_files)
    script = (f"read_verilog -sv {files}; synth -top {top} -noabc; "
              f"write_json {out_json}")
    r = core.run(ys + ["-p", script], cwd, timeout=timeout)
    p = os.path.join(cwd, out_json)
    return p if r["ok"] and os.path.exists(p) else None


def gate_schematic(rtl_files, cwd, top, out_png, timeout=900) -> str | None:
    """Layered node-link schematic from the synthesised yosys netlist."""
    npath = netlist_json(rtl_files, cwd, top, "_netlist.json", timeout)
    if not npath:
        return None
    data = json.load(open(npath, encoding="utf-8"))
    mod = (data.get("modules") or {}).get(top)
    if not mod:
        return None
    cells = mod.get("cells") or {}
    ports = mod.get("ports") or {}
    nodes, edges = [], []
    for name, c in cells.items():
        t = c.get("type", "")
        nodes.append({"id": name, "label": _short(t), "kind": _kind(t)})
    idx = {n["id"]: n for n in nodes}
    # build edges from bit ids: cells reference wires by number, so map bit
    # numbers to the first cell driving them
    driver = {}
    for name, c in cells.items():
        for pname, bits in (c.get("connections") or {}).items():
            if pname in ("Y", "Q", "X"):
                for b in (bits or []):
                    if isinstance(b, int):
                        driver[b] = name
    for name, c in cells.items():
        for pname, bits in (c.get("connections") or {}).items():
            if pname in ("Y", "Q", "X"):
                continue
            for b in (bits or []):
                if isinstance(b, int) and b in driver and driver[b] != name:
                    edges.append((driver[b], name))

    # layered layout
    import collections
    adj = collections.defaultdict(list)
    indeg = collections.defaultdict(int)
    for a, b in edges:
        adj[a].append(b)
        indeg[b] += 1
    lvl = {}
    q = collections.deque([n["id"] for n in nodes if indeg[n["id"]] == 0])
    for n in q:
        lvl[n] = 0
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in lvl or lvl[v] < lvl[u] + 1:
                lvl[v] = lvl[u] + 1
                q.append(v)
    for n in nodes:
        lvl.setdefault(n["id"], 0)
    by = collections.defaultdict(list)
    for n in nodes:
        by[lvl[n["id"]]].append(n)
    maxl = max(by) if by else 0
    W = max(900, (maxl + 1) * 150)
    rows = max((len(v) for v in by.values()), default=1)
    H = max(300, rows * 34 + 60)
    pos = {}
    for L, ns in by.items():
        for i, n in enumerate(ns):
            pos[n["id"]] = (30 + L * 150, 40 + i * 34)

    Image, ImageDraw, _ = _pil()
    img = Image.new("RGB", (W, H), (16, 20, 28))
    dr = ImageDraw.Draw(img)
    f = _font(10)
    for a, b in edges:
        if a in pos and b in pos:
            x1, y1 = pos[a]
            x2, y2 = pos[b]
            dr.line([(x1 + 110, y1 + 10), (x2, y2 + 10)],
                    fill=(70, 90, 120), width=1)
    colors = {"ff": (200, 120, 220), "mux": (110, 170, 230),
              "and": (120, 220, 150), "or": (230, 200, 110),
              "xor": (230, 140, 120), "not": (170, 170, 200),
              "cell": (150, 160, 180)}
    for n in nodes:
        x, y = pos[n["id"]]
        col = colors.get(n["kind"], (150, 160, 180))
        dr.rounded_rectangle([x, y, x + 108, y + 20], 3, fill=(30, 36, 48),
                             outline=col, width=1)
        dr.text((x + 4, y + 4), n["label"][:16], fill=col, font=f)
    dr.text((8, 8), f"gate schematic — {top} ({len(cells)} cells, "
                    f"{len(edges)} edges)", fill=(140, 150, 170), font=f)
    img.save(out_png)
    return out_png


def _short(t):
    return (t.replace("$_", "").replace("_$", "").replace("__", "_")
            .strip("_")[:16] or "?")


def _kind(t):
    for k, sub in (("ff", "DFF"), ("mux", "MUX"), ("and", "AND"),
                   ("or", "OR"), ("xor", "XOR"), ("not", "NOT")):
        if sub in t:
            return k
    return "cell"


# ------------------------------------------------------------------ 2D die
def composition_diagram(comp: dict, out_png: str, w=940, h=440) -> str:
    """Draw the instance graph of a composed chip (blocks + nets)."""
    Image, ImageDraw, _ = _pil()
    img = Image.new("RGB", (w, h), (14, 18, 26))
    dr = ImageDraw.Draw(img)
    f = _font(12)
    fs = _font(11)
    fb = _font(16)
    blocks = comp.get("blocks") or []
    nets = comp.get("nets") or []
    dr.text((18, 10),
            f"{comp.get('name', 'chip')} — composition ({len(blocks)} blocks, "
            f"{len(nets)} nets)", fill=(220, 228, 240), font=fb)
    if not blocks:
        img.save(out_png)
        return out_png
    cols = min(4, max(1, len(blocks)))
    bw, bh, gap = 160, 78, 70
    pos = {}
    for i, b in enumerate(blocks):
        r, c = divmod(i, cols)
        x = 24 + c * (bw + gap)
        y = 56 + r * (bh + 90)
        pos[b["inst"]] = (x, y)

    back = 0
    for i, nt in enumerate(nets):
        drv = str(nt.get("driver") or "").split(".")[0]
        if drv not in pos:
            continue
        x1, y1 = pos[drv]
        stagger = (i % 3 - 1) * 10
        for s in nt.get("sinks") or []:
            si = str(s).split(".")[0]
            if si not in pos:
                continue
            x2, y2 = pos[si]
            colour = (120, 200, 150) if nt.get("top") != "output" \
                else (230, 190, 110)
            label = str(nt.get("name", ""))
            if x2 > x1:
                ya = y1 + bh // 2 + stagger
                yb = y2 + bh // 2 + stagger
                xa, xb = x1 + bw, x2
                dr.line([xa, ya, xb, yb], fill=colour, width=2)
                mid, ly = (xa + xb) // 2, (ya + yb) // 2
            else:
                # backward edge: route underneath so it does not cross blocks
                ya = y1 + bh // 2 + (i % 2) * 6
                yb = y2 + bh // 2 + (i % 2) * 6
                ylow = y1 + bh + 24 + back * 13
                back += 1
                dr.line([x1, ya, x1 - 12, ya, x1 - 12, ylow,
                         x2 + bw + 12, ylow, x2 + bw + 12, yb, x2 + bw, yb],
                        fill=colour, width=2, joint="curve")
                mid, ly = (x1 + x2 + bw) // 2, ylow
            if label:
                tw = dr.textlength(label, font=fs)
                lx = mid - tw / 2
                if lx > 8:
                    dr.rectangle([lx - 2, ly - 7, lx + tw + 2, ly + 7],
                                 fill=(14, 18, 26))
                    dr.text((lx, ly - 6), label, fill=(150, 170, 195), font=fs)

    for b in blocks:
        x, y = pos[b["inst"]]
        dr.rectangle([x, y, x + bw, y + bh], fill=(28, 36, 50),
                     outline=(90, 150, 220), width=2)
        dr.text((x + 9, y + 8), b["kind"], fill=(205, 220, 240), font=f)
        dr.text((x + 9, y + 29), b["inst"], fill=(150, 200, 240), font=f)
        dr.text((x + 9, y + 50), b.get("module", ""),
                fill=(135, 148, 168), font=f)
    img.save(out_png)
    return out_png


def die_map(stats: dict, top: str, out_png: str, w=520, h=340) -> str:
    """Simple area map: tiles proportional to cell-type counts."""
    Image, ImageDraw, _ = _pil()
    img = Image.new("RGB", (w, h), (14, 18, 26))
    dr = ImageDraw.Draw(img)
    f = _font(12)
    fb = _font(16)
    types = sorted((stats.get("cell_types") or {}).items(),
                   key=lambda kv: -kv[1])
    total = sum(n for _t, n in types) or 1
    palette = [(90, 150, 220), (120, 200, 150), (230, 190, 110),
               (200, 130, 210), (230, 140, 120), (140, 170, 200),
               (170, 210, 120), (210, 160, 120)]
    x, y, row_h = 16, 44, 0
    info = None
    if stats.get("fmax_mhz") is not None:
        info = (f"{stats.get('device', 'hx8k')}/{stats.get('package', 'ct256')}"
                f"   LC {stats.get('lc_used', '?')}/"
                f"{stats.get('lc_available', '?')}   "
                f"Fmax {stats['fmax_mhz']:.1f} MHz "
                f"({'met' if stats.get('timing_met') else 'MISSED'})")
    elif stats.get("lc_available"):
        info = (f"{stats.get('device', 'hx8k')}   LC "
                f"{stats.get('lc_used', '?')}/{stats.get('lc_available')}   "
                f"(combinational, no clock)")
    if info:
        dr.text((16, 32), info, fill=(150, 200, 240), font=f)
        y = 62
    avail_h = h - (108 if info else 90)
    for i, (t, n) in enumerate(types):
        frac = n / total
        tw = max(10, int(frac * (w - 32)))
        th = max(10, int(frac * avail_h))
        if x + tw > w - 16:
            x = 16
            y += row_h + 6
            row_h = 0
        dr.rectangle([x, y, x + tw, y + th], fill=palette[i % len(palette)],
                     outline=(20, 24, 32))
        dr.text((x + 3, y + 3), f"{_short(t)} {n}", fill=(20, 24, 32), font=f)
        x += tw + 6
        row_h = max(row_h, th)
    dr.text((16, 12), f"{top} — area map ({total} cells)",
            fill=(220, 228, 240), font=fb)
    img.save(out_png)
    return out_png


# ------------------------------------------------------------------ 3D
def die_3d(stats: dict, top: str, out_base: str, formats=("glb", "png")):
    """Build a 3D die/package model (substrate + die + pins) and export."""
    import threed
    m = threed.Mesh(name=f"{top}_package")
    # package body
    m.add(threed.box(3.0, 0.35, 3.0), (0, 0, 0))
    # die (scaled a little by cell count for flavour, capped)
    cells = max(1, int(stats.get("cells") or 1))
    s = min(1.6, 0.8 + cells / 400.0)
    m.add(threed.box(s, 0.18, s), (0, 0.26, 0))
    # pins on all four sides
    n = 10
    for i in range(n):
        t = (i / (n - 1) - 0.5) * 2.6
        m.add(threed.box(0.16, 0.12, 0.5), (t, -0.22, 1.55))
        m.add(threed.box(0.16, 0.12, 0.5), (t, -0.22, -1.55))
        m.add(threed.box(0.5, 0.12, 0.16), (1.55, -0.22, t))
        m.add(threed.box(0.5, 0.12, 0.16), (-1.55, -0.22, t))
    files = {}
    if "png" in formats:
        files["png"] = threed.render_png(m, out_base + ".png", w=640, h=480)
    if any(f in formats for f in ("glb", "obj", "stl", "fbx")):
        files.update(threed.export_mesh(
            m, out_base, [f for f in formats if f != "png"]))
    return files


def make_all(cwd: str, top: str, stats: dict, outdir: str | None = None,
             formats=("glb", "fbx", "png")):
    """Generate every 2D/3D view for a verified design."""
    outdir = outdir or cwd
    os.makedirs(outdir, exist_ok=True)
    rtl_files = [f for f in os.listdir(cwd)
                 if f.endswith((".v", ".sv")) and not f.startswith("tb_")]
    main_rtl = os.path.join(cwd, f"{top}.v")
    if not os.path.exists(main_rtl) and rtl_files:
        main_rtl = os.path.join(cwd, rtl_files[0])
    res = {}
    try:
        res["block"] = block_diagram(main_rtl,
                                     os.path.join(outdir, f"{top}-block.png"))
    except Exception as e:
        res["block"] = f"error: {e}"
    try:
        res["schematic"] = gate_schematic(
            rtl_files, cwd, top, os.path.join(outdir, f"{top}-schematic.png"))
    except Exception as e:
        res["schematic"] = f"error: {e}"
    try:
        res["die_map"] = die_map(stats, top,
                                 os.path.join(outdir, f"{top}-die.png"))
    except Exception as e:
        res["die_map"] = f"error: {e}"
    try:
        res.update({"3d_" + k: v for k, v in die_3d(
            stats, top, os.path.join(outdir, f"{top}-package"),
            formats=formats).items()})
    except Exception as e:
        res["3d"] = f"error: {e}"
    return res
