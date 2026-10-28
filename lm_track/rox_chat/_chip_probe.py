import json
import time
import urllib.request

MODEL = "chip-design-ai-v4"
URL = "http://localhost:11434/api/chat"


def chat(prompt, timeout=180):
    payload = {"model": MODEL, "messages": [{"role": "user",
               "content": prompt}], "stream": False,
               "options": {"temperature": 0.2, "num_ctx": 8192}}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    out = (d.get("message") or {}).get("content") or ""
    print(f"[probe] {time.time()-t0:.1f}s | {len(out)} chars\n{out[:1600]}\n")


print("=== PROBE 1: plan a module's ports from a description ===")
chat("You are designing a small RISC-V-alike 4-bit CPU in Verilog. "
     "Describe the exact module `cpu_top` port list: every port name, "
     "direction (input/output), and width. Output the Verilog module "
     "header only.")

print("=== PROBE 2: review a module vs a contract ===")
chat("Here is a Verilog ALU and a required interface contract. "
     "Check whether the ALU's ports EXACTLY match the contract, and list "
     "any mismatches.\nCONTRACT: module alu(a[3:0], b[3:0], op[1:0], "
     "y[3:0], zero, carry) — 6 ports.\nRTL:\nmodule alu(input [3:0] a, b, "
     "input [1:0] op, output reg [3:0] y, output zero, carry);\n  always "
     "@(*) begin case(op) 2'b00:{carry,y}=a+b; 2'b01:{carry,y}=a-b; "
     "default:{carry,y}=a; endcase end\n  assign zero=(y==0);\nendmodule")