"""RTL generation + repair using a local Ollama model.

The model is the *composition* layer: deterministic generators handle the
common blocks (perfect by construction), and the model writes glue/novel
logic, which then has to pass the same hard gate.

Model choice is RAM-aware so it never pushes the machine into the crash
territory we hit earlier:
    free >= 13 GB -> qwen2.5-coder:14b
    free >=  8 GB -> qwen2.5-coder:7b
    otherwise     -> no model (deterministic only)
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

OLLAMA = os.environ.get("ROX_OLLAMA", "http://localhost:11434")
LADDER = [("qwen2.5-coder:14b", 13.0), ("qwen2.5-coder:7b", 8.0)]

# Hosted inference (Nebius Token Factory, OpenAI-compatible, running on
# NVIDIA GPUs). Set NEBIUS_API_KEY to use it; without a key everything
# stays local.
NEBIUS_URL = os.environ.get("ROX_NEBIUS_URL",
                            "https://api.studio.nebius.com/v1")
NEBIUS_KEY = os.environ.get("NEBIUS_API_KEY", "")
# The hackathon is scored on Nemotron. 70B is the sweet spot for RTL: strong
# enough for code, cheap enough to iterate. Override for the 340B or the Mini.
NEBIUS_MODEL = os.environ.get("ROX_NEBIUS_MODEL",
                              "nvidia/llama-3.1-nemotron-70b-instruct")
# Other hosted Nemotron variants worth trying (check `/models` for the exact
# ids your account can see):
NEMOTRON_VARIANTS = [
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "nvidia/nemotron-4-340b-instruct",
    "nvidia/Nemotron-Mini-4B-Instruct",
]


def _key() -> str:
    """Read the key dynamically so a runtime env change takes effect."""
    return os.environ.get("NEBIUS_API_KEY", NEBIUS_KEY)


def provider() -> str:
    """'nebius' when a hosted endpoint is configured, else 'ollama'."""
    force = os.environ.get("ROX_LLM_PROVIDER", "auto").lower()
    if force in ("nebius", "nvidia", "openai"):
        return "nebius"
    if force == "ollama":
        return "ollama"
    return "nebius" if _key() else "ollama"


def provider_status() -> dict:
    return {"provider": provider(), "model": pick_model(),
            "endpoint": (NEBIUS_URL if provider() == "nebius" else OLLAMA),
            "key_present": bool(NEBIUS_KEY)}


def _ssl_ctx():
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _chat_nebius(messages, model, temperature, num_predict, timeout) -> str:
    payload = {"model": model, "messages": messages,
               "temperature": float(temperature),
               "max_tokens": int(num_predict)}
    try:
        req = urllib.request.Request(
            NEBIUS_URL.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {_key()}",
                     "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=_ssl_ctx()) as r:
            d = json.loads(r.read().decode())
        return ((d.get("choices") or [{}])[0].get("message") or {}).get(
            "content", "").strip()
    except Exception:
        return ""


def list_models(timeout=30) -> list:
    """Model ids the configured endpoint exposes (needs a key)."""
    if not _key():
        return []
    try:
        req = urllib.request.Request(
            NEBIUS_URL.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {_key()}"})
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=_ssl_ctx()) as r:
            d = json.loads(r.read().decode())
        return sorted(m.get("id", "") for m in (d.get("data") or [])
                      if m.get("id"))
    except Exception:
        return []


def _get(path, timeout=20):
    try:
        with urllib.request.urlopen(OLLAMA + path, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def installed() -> list:
    d = _get("/api/tags") or {}
    return [m.get("name", "") for m in (d.get("models") or [])]


def loaded() -> list:
    d = _get("/api/ps") or {}
    return [m.get("name", "") for m in (d.get("models") or [])]


def free_ram_gb() -> float:
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MS()
        st.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullAvailPhys / (1024 ** 3)
    except Exception:
        return 0.0


def pick_model() -> str | None:
    if provider() == "nebius":
        return NEBIUS_MODEL
    have = installed()
    live = loaded()
    free = free_ram_gb()
    # A model already resident is already paid for in RAM â€” use it.
    for name, _need in LADDER:
        if any(l == name or l.startswith(name) for l in live):
            return name
    for name, need in LADDER:
        if free >= need and any(h == name or h.startswith(name)
                                for h in have):
            return name
    return None


def chat(messages, model=None, temperature=0.15, num_ctx=8192,
         num_predict=1600, timeout=900) -> str:
    model = model or pick_model()
    if not model:
        return ""
    if provider() == "nebius":
        # ignore local Ollama names; a HF repo id may be passed explicitly
        nm = model if "/" in str(model) else NEBIUS_MODEL
        return _chat_nebius(messages, nm, temperature, num_predict, timeout)
    payload = {"model": model, "messages": messages, "stream": False,
               "keep_alive": "5m",
               "options": {"temperature": temperature, "num_ctx": num_ctx,
                           "num_predict": num_predict, "num_thread": 6}}
    try:
        req = urllib.request.Request(
            OLLAMA + "/api/chat", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return ((d.get("message") or {}).get("content") or "").strip()
    except Exception:
        return ""


_CODE = re.compile(r"```(?:verilog|systemverilog|v)?\s*\n(.*?)```", re.S)


def extract_verilog(text: str) -> str:
    if not text:
        return ""
    m = _CODE.search(text)
    body = m.group(1) if m else text
    i = body.find("module ")
    if i > 0:
        body = body[i:]
    j = body.rfind("endmodule")
    if j >= 0:
        body = body[:j + len("endmodule")]
    return body.strip() + "\n" if body.strip() else ""


_SYS = (
    "You are an expert digital design engineer. Write SYNTHESIZABLE "
    "Verilog-2001/2003. Rules: one module per answer; no testbench; no "
    "$display/$finish/$fatal; no delays. Every output must be driven in "
    "EXACTLY ONE place: never mix an `assign` with an always block for the "
    "same signal, and never assign the same reg from two always blocks. "
    "For purely combinational functions (comparator, ALU, mux, decoder) use "
    "`always @(*)` with blocking assignments and declare the outputs as "
    "`reg`. Only use `always @(posedge clk)` when the specification asks for "
    "a register/counter/state machine; there use non-blocking assignments. "
    "Reset input is active-high 'rst'. Return only the module in one "
    "```verilog code block.")


def generate_rtl(spec: str, top: str | None = None,
                 ports: list | None = None, model=None) -> dict:
    """Ask the model for a module. Returns {ok, top, rtl, model}."""
    m = model or pick_model()
    if not m:
        return {"ok": False, "rtl": "", "model": None,
                "reason": "no model fits in RAM (deterministic only)"}
    port_txt = ""
    if ports:
        port_txt = "\nPorts (use exactly these names and directions):\n" + \
            "\n".join(ports)
    tname = f"\nModule name: {top}" if top else ""
    msg = [{"role": "system", "content": _SYS},
           {"role": "user", "content":
            f"Design this chip block.{tname}{port_txt}\n\nSpecification:\n"
            f"{spec}\n\nReturn only the Verilog module."}]
    text = chat(msg, model=m)
    rtl = extract_verilog(text)
    if not rtl or not is_complete(rtl):
        text = chat(msg, model=m, num_predict=2800)
        rtl = extract_verilog(text) or rtl
    if not rtl:
        return {"ok": False, "rtl": "", "model": m, "reason": "empty reply"}
    if not top:
        mm = re.search(r"\bmodule\s+([A-Za-z_]\w*)", rtl)
        top = mm.group(1) if mm else None
    return {"ok": True, "rtl": rtl, "top": top, "model": m}


def repair_rtl(rtl: str, top: str, errors: str, model=None,
               tb: str | None = None) -> dict:
    """Feed the toolchain errors back and ask for a corrected module.

    When the independent testbench is passed in, it is shown to the model as
    the authority: the RTL must change, not the test.
    """
    m = model or pick_model()
    if not m:
        return {"ok": False, "rtl": rtl, "model": None}
    tbtxt = ""
    if tb:
        tbtxt = ("\nThe testbench below is CORRECT and must pass unchanged.\n"
                 "Do not modify it. Fix the RTL only.\n"
                 f"```verilog\n{tb[:6000]}\n```\n")
    msg = [{"role": "system", "content": _SYS},
           {"role": "user", "content":
            f"This module `{top}` failed the toolchain:\n\n{rtl}\n"
            f"{tbtxt}\nErrors:\n{errors[:2500]}\n\nFix the RTL so the "
            f"testbench passes. Keep the same module name and ports. "
            f"Return only the corrected module."}]
    text = chat(msg, model=m)
    fixed = extract_verilog(text)
    return {"ok": bool(fixed), "rtl": fixed or rtl, "model": m}


_TB_SYS = """You are a senior digital designer. Output ONLY the requested
Verilog. Everything must be plain Verilog-2001 that compiles with iverilog 12,
lints with Verilator 5 and synthesises with yosys 0.33.

Hard constraints:
- NO SystemVerilog: no logic, no always_ff/always_comb, no interfaces,
  no packed arrays in ports, no '{...} assignment patterns
- never declare an array in the testbench and never assign to an array
- declare every signal as reg or wire
- the DUT must be synthesizable; only the testbench may use $display,
  $fatal, # delays and initial blocks"""

_TB_ASK = """Write a synthesizable Verilog module and a self-checking testbench.

Module name: {top}
Specification:
{spec}

Reply in EXACTLY this format and nothing else (no markdown fences):
=== RTL ===
<the module {top}>
=== TB ===
<the testbench, module tb_{top}>

Testbench rules:
- instantiate the design as `uut` with named port connections
- drive real stimulus with # delays, compare outputs against expected values
  one at a time with `if (out !== expected)`
- use scalar/vector regs only, never an array
- on success print exactly "{top}:PASS"
- on any mismatch print "{top}:FAIL ..." and call $fatal(1, "...")
- include an initial block that waits a timeout then prints
  "{top}:FAIL timeout" and calls $fatal(1, "timeout")
- never print PASS unconditionally
- never mix blocking and non-blocking assignments to the same variable
- keep it small: at most ~30 test vectors

Follow this exact testbench style (error counter, explicit vectors, timeout):

```
`timescale 1ns/1ps
module tb_example;
    reg [3:0] a;
    wire [3:0] y;
    integer errors = 0;
    example uut(.a(a), .y(y));
    initial begin
        a = 4'd0; #10;
        if (y !== 4'd0) begin
            $display("example:FAIL a=%0d y=%0d", a, y);
            errors = errors + 1;
        end
        a = 4'd5; #10;
        if (y !== 4'd5) begin
            $display("example:FAIL a=%0d y=%0d", a, y);
            errors = errors + 1;
        end
        if (errors == 0) $display("example:PASS");
        else $fatal(1, "example:FAIL");
        $finish;
    end
    initial begin
        #10000;
        $display("example:FAIL timeout");
        $fatal(1, "example:FAIL timeout");
    end
endmodule
```"""


def _normalise(src: str, name: str) -> str:
    src = src or ""
    # strip markdown code fences the model likes to add
    src = re.sub(r"^[ \t]*```[A-Za-z0-9_+-]*[ \t]*$", "", src, flags=re.M)
    src = src.strip() + "\n"
    m = re.search(r"\bmodule\s+([A-Za-z_]\w*)", src)
    if m and m.group(1) != name:
        src = src[:m.start(1)] + name + src[m.end(1):]
    return src


def _split_rtl_tb(text: str, top: str):
    if not text:
        return None, None
    m = re.search(r"===\s*RTL\s*===(.*?)===\s*TB\s*===(.*)",
                  text, re.S | re.I)
    if m:
        rtl, tb = m.group(1), m.group(2)
    else:
        mods = re.findall(r"(?ms)module\b.*?endmodule", text)
        if len(mods) < 2:
            return None, None
        rtl, tb = mods[0], mods[1]
    return _normalise(rtl, top), _normalise(tb, "tb_" + top)


def is_complete(src: str) -> bool:
    """True when the Verilog ends with endmodule (i.e. was not truncated)."""
    return bool(re.search(r"endmodule\s*$", (src or "").strip()))


def tb_sane(tb: str, top: str) -> tuple:
    """Cheap check that the testbench actually verifies something."""
    if not tb:
        return False, "no testbench"
    if not is_complete(tb):
        return False, "truncated (no endmodule)"
    if f"tb_{top}" not in tb:
        return False, "wrong tb module name"
    if f"{top}:PASS" not in tb:
        return False, "no PASS message"
    if "$fatal" not in tb:
        return False, "no $fatal on failure"
    checks = tb.count("!==") + tb.count("!=") + tb.count("if (")
    if checks < 3:
        return False, "too few checks"
    if "uut" not in tb and top not in tb:
        return False, "does not instantiate the DUT"
    return True, ""


def generate_rtl_tb(spec: str, top: str, model=None) -> dict:
    """Ask for a module AND a self-checking testbench in one reply."""
    m = model or pick_model()
    if not m:
        return {"ok": False, "rtl": "", "tb": "", "model": None,
                "reason": "no model fits in RAM (deterministic only)"}
    msg = [{"role": "system", "content": _TB_SYS},
           {"role": "user", "content": _TB_ASK.format(top=top, spec=spec)}]
    text = chat(msg, model=m, num_predict=2200)
    rtl, tb = _split_rtl_tb(text, top)
    if not rtl:
        return {"ok": False, "rtl": "", "tb": "", "model": m,
                "reason": "could not parse RTL/TB"}
    ok_tb, why = tb_sane(tb, top)
    return {"ok": True, "rtl": rtl, "tb": tb or "", "model": m,
            "tb_ok": ok_tb, "tb_reason": why}


def repair_rtl_tb(rtl: str, tb: str, top: str, errors: str,
                  model=None) -> dict:
    """Feed errors back and ask for both files to be corrected."""
    m = model or pick_model()
    if not m:
        return {"ok": False, "rtl": rtl, "tb": tb, "model": None}
    msg = [{"role": "system", "content": _TB_SYS},
           {"role": "user", "content":
            f"The design `{top}` failed the toolchain.\n\n"
            f"=== RTL ===\n{rtl}\n=== TB ===\n{tb}\n\n"
            f"Errors:\n{errors[:2500]}\n\n"
            f"Fix it. Keep the module name `{top}` and the testbench module "
            f"`tb_{top}`. Reply in the same === RTL === / === TB === format."}]
    text = chat(msg, model=m, num_predict=2200)
    r2, t2 = _split_rtl_tb(text, top)
    return {"ok": bool(r2), "rtl": r2 or rtl, "tb": t2 or tb, "model": m}


_TB_ONLY_SYS = """You write Verilog testbenches. Plain Verilog-2001 for
iverilog 12. No SystemVerilog, no arrays, no interfaces."""

_TB_ONLY_ASK = """Write ONLY a self-checking testbench for this specification.

Module name: {top}
Ports (exact names, directions and widths):
{ports}

Specification:
{spec}

Rules:
- declare `module tb_{top};` and instantiate `{top} uut (...)` with named
  port connections
- **if the module has a `clk` port you MUST add a clock generator
  `always #5 clk = ~clk;`** and drive stimulus so the design sees clock edges
- derive every expected value from the SPECIFICATION. Do not assume any
  particular implementation.
- use scalar/vector regs only, never an array
- use # delays, compare one output at a time with `if (x !== expected)`
- print "{top}:PASS" only if every check passed
- on a mismatch print "{top}:FAIL ..." and call $fatal(1, "...")
- include an initial block that waits a timeout, prints
  "{top}:FAIL timeout" and calls $fatal(1, "timeout")
- at most ~12 vectors, keep the whole testbench under 120 lines
- reply with the testbench only, no markdown fences"""


def generate_tb(spec: str, top: str, ports: str, model=None) -> dict:
    """Write an independent testbench from the spec + interface only."""
    m = model or pick_model()
    if not m:
        return {"ok": False, "tb": "", "model": None,
                "reason": "no model fits in RAM"}
    msg = [{"role": "system", "content": _TB_ONLY_SYS},
           {"role": "user", "content": _TB_ONLY_ASK.format(
               top=top, spec=spec, ports=ports)}]
    tb = ""
    for _attempt in range(2):
        text = chat(msg, model=m, num_predict=4000)
        tb = _normalise(text, "tb_" + top)
        tb = ensure_clock(tb)
        if is_complete(tb):
            break
    ok_tb, why = tb_sane(tb, top)
    return {"ok": bool(tb.strip().startswith("`timescale")
                       or "module" in tb), "tb": tb,
            "tb_ok": ok_tb, "tb_reason": why, "model": m}


_RTL_VS_TB = """You are a senior digital designer. Write a synthesizable
Verilog module that PASSES the testbench below exactly. Treat the testbench
as the acceptance criteria: every expected value in it is correct.

Module name: {top}
Ports:
{ports}

Specification:
{spec}

The module must pass this testbench:
{tb}

Rules:
- plain Verilog-2001, synthesizable with yosys 0.33
- no SystemVerilog, no arrays in ports, no assignment patterns
- do not modify or re-emit the testbench
- reply with the module only, no markdown fences"""


def generate_rtl_vs_tb(spec: str, top: str, ports: str, tb: str,
                       model=None) -> dict:
    """Write the RTL against an independently written testbench."""
    m = model or pick_model()
    if not m:
        return {"ok": False, "rtl": "", "model": None,
                "reason": "no model fits in RAM"}
    msg = [{"role": "system", "content": _TB_ONLY_SYS},
           {"role": "user", "content": _RTL_VS_TB.format(
               top=top, ports=ports, spec=spec, tb=tb[:6000])}]
    text = chat(msg, model=m, num_predict=1800)
    rtl = _normalise(extract_verilog(text) or text, top)
    return {"ok": bool("module" in rtl), "rtl": rtl, "model": m}


def ensure_clock(tb: str) -> str:
    """Guarantee a clock generator in a testbench that drives a `clk` port.

    Small models routinely write `clk = 0` and never toggle it, which makes
    every clocked design time out. This is a deterministic fix.
    """
    if not tb or "clk" not in tb:
        return tb
    if re.search(r"always\s*#\s*\d+\s*(clk|CLK)\s*=\s*~(clk|CLK)", tb):
        return tb
    tb = re.sub(r"\bwire(\s+)clk\b", r"reg\1clk", tb)
    tb = re.sub(r"\bwire(\s+)CLK\b", r"reg\1CLK", tb)
    gen = "    always #5 clk = ~clk;\n"
    m = re.search(r"\n[ \t]*initial\b", tb)
    if m:
        return tb[:m.start()] + "\n" + gen + tb[m.start():]
    m = re.search(r"\)\s*;", tb)
    if m:
        return tb[:m.end()] + "\n" + gen + tb[m.end():]
    return tb


def unload(model=None):
    if provider() == "nebius":
        return
    m = model or pick_model()
    if not m:
        return
    try:
        req = urllib.request.Request(
            OLLAMA + "/api/generate",
            data=json.dumps({"model": m, "keep_alive": 0}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass

if __name__ == "__main__":
    import sys

    print(json.dumps(provider_status(), indent=1))
    if "--models" in sys.argv:
        ids = list_models()
        if not ids:
            print("no model list (missing key or endpoint unreachable)")
        for mid in ids:
            mark = "  <- default" if mid == NEBIUS_MODEL else ""
            print(" ", mid, mark)