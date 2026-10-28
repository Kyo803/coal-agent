"""Per-module behavior testbenches — the correctness backbone for chips.

For each leaf RTL module we write a deterministic testbench header (exact
port wiring from the *generated* module) and ask the model only to fill the
stimulus/assert block. The TB is compiled with `-s tb_<mod>` and must print
`<MOD>:PASS` (else `$fatal`), so a module is only trusted after its own
behavior is proven in isolation.
"""
from __future__ import annotations

import posixpath

from sandbox import sb

from . import generator as GEN


def _mod_meta(cwd: str, mod_rel: str) -> dict | None:
    from chip_architect import ChipArchitect
    src = sb.read_text(posixpath.join(cwd, mod_rel))
    if not src:
        return None
    a = ChipArchitect()
    return {"name": a.extract_module_name(src),
            "ports": a.extract_ports(src), "src": src}


def _tb_rel(modname: str) -> str:
    return f"tb_{modname}.v"


def build_behavior_tb(cwd: str, mod_rel: str, behavior: str = "",
                      tries: int = 1) -> dict:
    meta = _mod_meta(cwd, mod_rel)
    if not meta or not meta["name"] or not meta["ports"]:
        return {"ok": False, "reason": "no module/ports", "tries": 0}
    modname = meta["name"]
    tb_rel = _tb_rel(modname)
    dest = posixpath.join(cwd, tb_rel)

    decl, conn = [], []

    def _w(p):
        w = p.get("width") or "1"
        return "" if w in ("", "1") else w

    for p in meta["ports"]:
        n = p.get("name")
        w = _w(p)
        if p.get("dir") == "input":
            decl.append(("    reg %s %s;" % (w, n)).replace("  ", " "))
        else:
            decl.append(("    wire %s %s;" % (w, n)).replace("  ", " "))
        conn.append(f".{n}({n})")
    header = (f"// AUTO behavior testbench for {modname}\n"
              f"`timescale 1ns/1ps\nmodule {tb_rel[:-2]};\n"
              + "\n".join(decl) + "\n"
              f"    {modname} uut (\n        {', '.join(conn)}\n    );\n\n")

    ports_txt = "\n".join(f"  {p['dir']} {_w(p)} {p.get('name')}"
                          for p in meta["ports"])
    sys = ("You are writing a Verilog testbench BODY only. Output the "
           "statements that go inside an `initial begin ... end` block: "
           "drive the inputs over time with realistic clocks/values, assert "
           "the expected outputs described in BEHAVIOR, and end with "
           f"`if (__errors == 0) $display(\"{modname}:PASS\"); else "
           "$fatal(1);`. No module/endmodule, no new declarations, no "
           "explanations.")
    default = f"exercise all inputs; assert sane outputs; print {modname}:PASS"
    user = (f"MODULE: {modname}\nPORTS:\n{ports_txt}\n\n"
            f"BEHAVIOR:\n{behavior or default}")
    last = {"ok": False}
    for i in range(max(1, tries)):
        body = GEN._chat([{"role": "system", "content": sys},
                          {"role": "user", "content": user}],
                         max_tokens=800, temperature=0.2, thinking=False)
        body = (body or "").strip()
        body = re_body(body)
        if not body:
            continue
        close_v = (f'    if (__cnt == 0) $display("{modname}:PASS");\n'
                   "    else $fatal(1);\n")
        tb = header + body + "\n" + close_v + "    end\nendmodule\n"
        sb.write(dest, tb)
        r = sb.shell(
            f"cd {cwd!r} && iverilog -g2012 -s {tb_rel[:-2]} -o /tmp/rox_tb.out "
            f"{posixpath.basename(mod_rel)!r} {tb_rel!r} && "
            f"vvp /tmp/rox_tb.out", timeout=300)
        out = (r.get("out") or "") + (r.get("err") or "")
        ok = r["rc"] == 0 and f"{modname}:PASS" in out
        if ok:
            cause = "ok"
        elif ("FATAL" in out) or ("CHK fail" in out):
            cause = "behavior"
        else:
            cause = "tb"
        last = {"ok": ok, "cause": cause, "try": i + 1, "rc": r["rc"],
                "out": out[:600]}
        if ok:
            break
    if not last.get("ok") and last.get("cause") == "tb":
        sb.remove(dest)   # broken auto-TB must not block the full compile
    return last


def re_body(body: str) -> str:
    """Strip accidental module/endmodule/text so we only keep statements."""
    import re
    body = re.sub(r"(?si).*?initial\s+begin", "", body)
    body = re.sub(r"(?s)end\s*$", "", body)
    body = body.replace("endmodule", "").replace("`timescale", "")
    body = re.sub(r"\n\s*\$/", "\n$", body)
    return body.strip()