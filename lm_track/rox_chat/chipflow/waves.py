"""Waveform capture for a verified chip.

Runs the design's own testbench with VCD dumping, renders a monochrome
waveform PNG, and can hand the VCD to GTKWave.

Nothing here invents data: the VCD is produced by the simulator from the
same RTL the gate verified.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from . import core

MAX_SIGNALS = 14


def _top_of(text: str) -> str | None:
    m = re.search(r"\bmodule\s+([A-Za-z_]\w*)", text or "")
    return m.group(1) if m else None


def _rtl_files(d: str) -> list[str]:
    out = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".v") and not f.startswith("tb_") and \
                not f.startswith("_"):
            out.append(os.path.join(d, f))
    return out


def _tb_file(d: str, top: str, tb: str | None) -> str | None:
    cands = []
    if tb:
        cands.append(tb if tb.endswith(".v") else f"tb_{tb}.v")
    cands += [f"tb_{top}.v", f"test_{top}.v"]
    cands += [f for f in sorted(os.listdir(d))
              if f.startswith("tb_") and f.endswith(".v")]
    for c in cands:
        p = c if os.path.isabs(c) else os.path.join(d, c)
        if os.path.exists(p):
            return p
    return None


def _inject_dump(text: str, tb_mod: str, vcd: str) -> str:
    """Insert a $dumpfile/$dumpvars initial block after the module header."""
    i = text.find("module")
    if i < 0:
        raise ValueError("no module in testbench")
    depth, j = 0, i
    while j < len(text):
        ch = text[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ";" and depth <= 0:
            j += 1
            break
        j += 1
    block = (f'\ninitial begin $dumpfile("{vcd}"); '
             f"$dumpvars(0, {tb_mod}); end\n")
    return text[:j] + block + text[j:]


def capture(d: str, top: str, tb: str | None = None,
            open_gui: bool = False, timeout: int = 600) -> dict:
    """Compile with VCD dumping, run, and return artefact paths."""
    d = os.path.abspath(d)
    tb_path = _tb_file(d, top, tb)
    if not tb_path:
        return {"ok": False, "output": f"no testbench in {d}"}
    rtl = _rtl_files(d)
    if not rtl:
        return {"ok": False, "output": f"no RTL files in {d}"}

    src = open(tb_path, encoding="utf-8", errors="ignore").read()
    tb_mod = _top_of(src) or f"tb_{top}"
    vcd_name = f"{top}.vcd"
    tb_wave = f"_tb_{top}_wave.v"
    with open(os.path.join(d, tb_wave), "w", encoding="utf-8") as f:
        f.write(_inject_dump(src, tb_mod, vcd_name))

    # run_tool gets a cwd, so pass bare filenames: absolute Windows paths
    # lose their backslashes when the command is joined for WSL.
    rtl_names = [os.path.basename(f) for f in rtl]
    vvp = f"_{top}_wave.vvp"
    comp = core.run_tool(
        ["iverilog", "-g2012", "-s", tb_mod, "-o", vvp, tb_wave] + rtl_names,
        d, timeout=timeout)
    if not comp["ok"]:
        return {"ok": False, "output":
                f"wave compile failed:\n{comp['out'][-1500:]}"}
    run = core.run_tool(["vvp", vvp], d, timeout=timeout)

    vcd = os.path.join(d, vcd_name)
    if not os.path.exists(vcd):
        return {"ok": False, "output":
                f"simulator produced no VCD:\n{run['out'][-1200:]}"}

    png = os.path.join(d, f"{top}-wave.png")
    try:
        draw_wave(vcd, png, title=top)
    except Exception as e:
        png = None
        note = f"waveform render failed: {e}"
    else:
        note = None

    lines = [f"waves for {top}:",
             f"  vcd       : {vcd}",
             f"  png       : {png or 'n/a'}"]
    if note:
        lines.append(f"  note      : {note}")
    txt = run.get("out") or ""
    if ":PASS" in txt:
        lines.append("  sim       : PASS")
    elif ":FAIL" in txt:
        lines.append("  sim       : FAIL")
    if open_gui:
        g = which_gtkwave()
        if g:
            try:
                subprocess.Popen(
                    [g, vcd], cwd=d,
                    creationflags=getattr(subprocess,
                                          "DETACHED_PROCESS", 0))
                lines.append(f"  gtkwave   : opened ({g})")
            except Exception as e:
                lines.append(f"  gtkwave   : launch failed: {e}")
        else:
            lines.append("  gtkwave   : not installed")
    return {"ok": bool(png), "output": "\n".join(lines),
            "vcd": vcd, "png": png}


def which_gtkwave() -> str | None:
    g = core.tool("gtkwave")
    if g and os.path.exists(g):
        return g
    return shutil.which("gtkwave")


# ------------------------------------------------------------------ render
def _parse_vcd(path: str):
    """Return (signals, changes) where changes[sig] = [(t, value_str)]."""
    sigs, by_id = [], {}
    changes = {}
    t = 0
    depth = 0
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("$scope"):
                depth += 1
                continue
            if line.startswith("$upscope"):
                depth = max(0, depth - 1)
                continue
            if line.startswith("$var"):
                parts = line.split()
                if len(parts) >= 5:
                    width, sid, name = parts[2], parts[3], parts[4]
                    rng = ""
                    if len(parts) >= 6 and parts[5].startswith("["):
                        rng = parts[5].rstrip("$end").strip()
                    s = {"id": sid, "name": name, "width": int(width),
                         "range": rng, "depth": depth}
                    sigs.append(s)
                    by_id[sid] = s
                    changes[sid] = []
                continue
            if line.startswith("$"):
                continue
            if line.startswith("#"):
                try:
                    t = int(line[1:])
                except ValueError:
                    pass
                continue
            if line[0] in "01xXzZ":
                sid = line[1:]
                if sid in by_id:
                    changes[sid].append((t, line[0]))
            elif line[0] in "bB":
                parts = line.split()
                if len(parts) >= 2 and parts[1] in by_id:
                    changes[parts[1]].append((t, parts[0][1:]))
    return sigs, changes


def _pick(sigs):
    """One row per name (prefer the outermost scope), clock first."""
    best = {}
    for s in sigs:
        n = s["name"]
        if n not in best or s["depth"] < best[n]["depth"]:
            best[n] = s
    uniq = list(best.values())

    def rank(s):
        n = s["name"].lower()
        if n in ("clk", "clock", "clk_i"):
            return 0
        if "rst" in n or "reset" in n:
            return 1
        if s["width"] == 1:
            return 3
        return 2
    return sorted(uniq, key=rank)[:MAX_SIGNALS]


def draw_wave(vcd: str, out_png: str, title: str = "waveform") -> str:
    from PIL import Image, ImageDraw

    try:
        from .views import _font
        font = _font(13)
        small = _font(11)
    except Exception:                       # pragma: no cover
        from PIL import ImageFont
        font = small = ImageFont.load_default()

    sigs, changes = _parse_vcd(vcd)
    sigs = _pick(sigs)
    if not sigs:
        raise ValueError("no signals in VCD")

    tmax = 0
    for s in sigs:
        ch = changes.get(s["id"]) or []
        if ch:
            tmax = max(tmax, ch[-1][0])
    tmax = max(tmax, 1)

    label_w, pad, row_h = 168, 16, 30
    width = 1280
    height = pad * 2 + row_h * len(sigs) + 46
    img = Image.new("RGB", (width, height), "#0b0b0b")
    dr = ImageDraw.Draw(img)

    plot_x0 = label_w
    plot_x1 = width - pad - 96
    span = max(1, plot_x1 - plot_x0)
    top_y = pad + 34

    dr.text((pad, 12), f"{title}  ·  {os.path.basename(vcd)}",
            fill="#f2f2f2", font=font)
    dr.text((pad, 28), f"t = 0 … {tmax}", fill="#8a8a8a", font=small)

    # faint column grid every 10%
    for k in range(11):
        x = plot_x0 + span * k // 10
        dr.line([(x, top_y - 6), (x, height - pad)], fill="#1d1d1d")
        dr.text((x - 8, height - pad - 12), str(tmax * k // 10),
                fill="#5f5f5f", font=small)

    for row, s in enumerate(sigs):
        y0 = top_y + row * row_h
        hi, lo = y0 + 4, y0 + row_h - 9
        dr.text((pad, y0 + 5), s["name"] + (s["range"] or ""),
                fill="#c9c9c9", font=small)
        ch = changes.get(s["id"]) or []
        if not ch:
            dr.line([(plot_x0, lo), (plot_x1, lo)], fill="#2a2a2a")
            continue
        cur = ch[0][1]
        start_t = ch[0][0]
        prev_x = plot_x0 + span * start_t // tmax
        if s["width"] == 1:
            level = hi if cur in ("1", "z") else lo
            dr.line([(plot_x0, level), (prev_x, level)], fill="#4a4a4a")
        for (t, v) in ch[1:]:
            x = plot_x0 + span * t // tmax
            if s["width"] == 1:
                old = hi if cur in ("1", "z") else lo
                new = hi if v in ("1", "z") else lo
                dr.line([(prev_x, old), (x, old)], fill="#e6e6e6", width=2)
                if new != old:
                    dr.line([(x, old), (x, new)], fill="#e6e6e6", width=2)
            else:
                dr.line([(prev_x, (hi + lo) // 2), (x, (hi + lo) // 2)],
                        fill="#3a3a3a")
                if x - prev_x > 7:
                    try:
                        val = int(v, 2)
                        txt = f"{val:X}" if len(v) > 4 else str(val)
                    except ValueError:
                        txt = v
                    dr.text((prev_x + 3, y0 + 3), txt, fill="#dcdcdc",
                            font=small)
            cur, prev_x = v, x
        if s["width"] == 1:
            level = hi if cur in ("1", "z") else lo
            dr.line([(prev_x, level), (plot_x1, level)],
                    fill="#e6e6e6", width=2)
        else:
            dr.line([(prev_x, (hi + lo) // 2), (plot_x1, (hi + lo) // 2)],
                    fill="#3a3a3a")

    img.save(out_png)
    return out_png
