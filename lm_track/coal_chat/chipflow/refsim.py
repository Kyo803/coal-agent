"""Reference-model verification.

The weak link in model-written chips is that the RTL and the testbench are
both guesses. Here the expected behaviour comes from a **Python reference
model** written independently of the Verilog, and the testbench is *generated*
from that model:

    model.step(inputs) -> expected outputs   (one clock at a time)

The emitted testbench drives the DUT with the same stimulus that was fed to
the Python model and compares every output, every cycle. If the RTL and the
model disagree, the chip fails -- and both sides were written by different
means, so this is a genuine check rather than a mirror.

    tb = build_tb("counter8", ports, vectors, clocked=True)
"""
from __future__ import annotations


def _lit(width: int, value: int) -> str:
    value = int(value) & ((1 << width) - 1)
    return f"{width}'b{value:0{width}b}"


def _range(width: int) -> str:
    return "" if width <= 1 else f"[{width - 1}:0] "


def build_tb(top: str, ports: dict, vectors, clocked: bool,
             reset_cycles: int = 2, timeout_ns: int = 0) -> str:
    """Emit a self-checking testbench from reference-model vectors.

    ports   : {name: {"dir": "input"|"output", "width": n}}
    vectors : [(inputs: dict, outputs: dict), ...]
    """
    ins = {n: p for n, p in ports.items() if p["dir"] == "input"}
    outs = {n: p for n, p in ports.items() if p["dir"] == "output"}
    has_clk = "clk" in ins
    has_rst = "rst" in ins
    data_ins = {n: p for n, p in ins.items() if n not in ("clk", "rst")}

    L = ["`timescale 1ns/1ps", f"module tb_{top};"]
    if has_clk:
        L.append("    reg clk = 0;")
    if has_rst:
        L.append("    reg rst = 0;")
    for n, p in data_ins.items():
        L.append(f"    reg  {_range(p['width'])}{n};")
    for n, p in outs.items():
        L.append(f"    wire {_range(p['width'])}{n};")
    L.append("    integer errors = 0;")
    L.append("    integer vec = 0;")

    conns = []
    for n in ins:
        conns.append(f".{n}({n})")
    for n in outs:
        conns.append(f".{n}({n})")
    L.append(f"    {top} uut({', '.join(conns)});")
    if has_clk:
        L.append("    always #5 clk = ~clk;")

    L.append("    initial begin")
    for n in data_ins:
        L.append(f"        {n} = 0;")
    if has_clk and has_rst:
        L.append("        rst = 1;")
        L.append(f"        repeat ({reset_cycles}) @(posedge clk);")
        L.append("        #1 rst = 0;")

    checks = 0
    for idx, (vin, vout) in enumerate(vectors):
        for n, p in data_ins.items():
            L.append(f"        {n} = {_lit(p['width'], vin.get(n, 0))};")
        if has_clk:
            L.append("        @(posedge clk); #1;")
        else:
            L.append("        #1;")
        conds = []
        for n, p in outs.items():
            exp = _lit(p["width"], vout.get(n, 0))
            conds.append(f"{n} !== {exp}")
            checks += 1
        if conds:
            L.append(f"        vec = {idx};")
            L.append(f"        if ({' || '.join(conds)}) begin")
            fmt = " ".join(f"{n}=%b" for n in outs)
            vals = ", ".join(n for n in outs)
            L.append(f'            $display("{top}:FAIL vec=%0d {fmt}", vec, {vals});')
            L.append("            errors = errors + 1;")
            L.append("        end")

    L.append("        if (errors == 0) $display(\"%s:PASS\");" % top)
    L.append("        else $fatal(1, \"%s:FAIL\");" % top)
    L.append("        $finish;")
    L.append("    end")

    if not timeout_ns:
        per = 10 if has_clk else 2
        timeout_ns = max(1000, per * (len(vectors) + 10) * 4)
    L.append("    initial begin")
    L.append(f"        #{timeout_ns};")
    L.append(f'        $display("{top}:FAIL timeout");')
    L.append(f'        $fatal(1, "{top}:FAIL timeout");')
    L.append("    end")
    L.append("endmodule")
    L.append("")
    return "\n".join(L), checks


def check_vectors(name: str, vectors, outputs) -> list:
    """Sanity: every vector must carry all outputs."""
    problems = []
    for i, (_vin, vout) in enumerate(vectors):
        for o in outputs:
            if o not in vout:
                problems.append(f"{name}: vector {i} missing {o}")
    return problems
