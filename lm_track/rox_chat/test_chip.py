"""Chip-design test suite. Run:  python test_chip.py
Add --live to also test the chip-design-ai-v4 model calls.

Deterministic part (no model): port parsing, contract verification,
iverilog compile of fixture RTL.
"""
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LIVE = "--live" in sys.argv

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


from chip_architect import ChipArchitect
from tools.handlers_chip import chip_verify

a = ChipArchitect()

print("== 1. port parsing (comma-separated) ==")
alu = ("module alu(input [3:0] a, b, input [1:0] op, output reg [3:0] y, "
       "output zero, carry); endmodule")
ports = a.extract_ports(alu)
names = [p["name"] for p in ports]
check("parses a,b,op,y,zero,carry",
      names == ["a", "b", "op", "y", "zero", "carry"], str(names))
check("widths carried", ports[0]["width"] == "[3:0]"
      and ports[1]["width"] == "[3:0]", str(ports[:2]))

print("== 2. contract verification ==")
expected = [{"name": "a", "dir": "input"}, {"name": "b", "dir": "input"},
            {"name": "op", "dir": "input"}, {"name": "y", "dir": "output"},
            {"name": "zero", "dir": "output"},
            {"name": "carry", "dir": "output"}]
ok, miss, extra = a.verify_contract(alu, expected)
check("matching contract", ok and not miss and not extra, f"{miss}/{extra}")
bad = ("module alu(input [3:0] a, input [1:0] op, output reg [3:0] y);"
       " endmodule")
ok, miss, extra = a.verify_contract(bad, expected)
check("detects missing ports", not ok and "b" in miss and "carry" in miss,
      f"missing={miss}")

print("== 3. chip_verify tool ==")
d = tempfile.mkdtemp()
ctx = SimpleNamespace(workspace=d)
vp = os.path.join(d, "alu.v")
open(vp, "w", encoding="utf-8").write(alu)
r = chip_verify({"path": vp,
                 "expected": "input a, input b, input op, output y, "
                             "output zero, output carry"}, ctx)
check("chip_verify ok", "OK" in r["output"], r["output"])
r2 = chip_verify({"path": vp, "expected": "input a, output y"}, ctx)
check("chip_verify flags extra",
      "MISMATCH" in r2["output"] and "op" in r2["output"],
      r2["output"])

print("== 4. iverilog compiles fixture RTL ==")
try:
    from chipflow.core import iverilog_works as _ivl_works
    _IVL_OK = _ivl_works()
except Exception:
    _IVL_OK = None
iverilog = None
import shutil
cands = [shutil.which("iverilog"), "iverilog",
         r"C:\iverilog\bin\iverilog.exe",
         r"C:\msys64\ucrt64\bin\iverilog.exe",
         r"C:\msys64\mingw64\bin\iverilog.exe"]
for cand in cands:
    if not cand:
        continue
    if os.path.exists(cand):
        iverilog = cand
        break
    try:
        subprocess.run([cand, "-V"], capture_output=True, timeout=10)
        iverilog = cand
        break
    except Exception:
        pass
if iverilog and _IVL_OK is not False:
    fixtures = {
        "alu.v": alu,
        "counter.v": ("module counter(input clk, input rst, "
                      "output reg [3:0] q); always @(posedge clk) begin "
                      "if (rst) q <= 0; else q <= q + 1; end endmodule"),
        "fsm.v": ("module fsm(input clk, input go, output reg done); "
                  "localparam IDLE=0, RUN=1; reg state; always @(posedge "
                  "clk) begin case(state) IDLE: if(go) state<=RUN; "
                  "RUN: begin done<=1; state<=IDLE; end endcase end "
                  "endmodule"),
    }
    for name, code in fixtures.items():
        p = os.path.join(d, name)
        open(p, "w", encoding="utf-8").write(code)
        r = subprocess.run([iverilog, "-o", os.path.join(d, "out"),
                            p], capture_output=True, text=True, timeout=60,
                           creationflags=0x08000000)
        check(f"iverilog {name}", r.returncode == 0,
              (r.stderr or r.stdout)[-200:])
else:
    if iverilog and _IVL_OK is False:
        print("  [skip] iverilog cannot compile: Device Guard blocks "
              "ivl.exe (see CHIPS.md)")
    else:
        print("  [skip] iverilog not found")

print("== 5. chip architect model (--live) ==")
if LIVE:
    plan = a.plan_ports("a 4-bit ALU with add/sub/and/xor and zero, carry flags")
    check("plan returns ports", len(plan["ports"]) >= 4,
          str(plan["ports"]))
    contract = "\n".join(a.port_line(p) for p in a.extract_ports(alu))
    rev = a.review(alu, contract)
    check("review returns text", len(rev) > 20, rev[:80])
else:
    print("  [skip] run with --live to test chip-design-ai-v4")

print("=" * 40)
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)