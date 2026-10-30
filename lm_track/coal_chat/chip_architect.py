"""Chip architect: a specialized local model (chip-design-ai-v4, Qwen2 3.1B)
that plans RTL module interfaces and reviews Verilog against contracts.

Used to stop multi-module port drift: before Coal writes a .v module it can
ask the architect for the port list; after writing, it checks the module's
real ports against the intended contract.

  arch = ChipArchitect()
  ports = arch.extract_ports(module_text)      # deterministic parser
  plan = arch.plan_ports("a 4-bit ALU")        # model proposes ports
  report = arch.review(rtl, contract)          # model checks the match

Runs on CPU via Ollama (no GPU contention). Fast (3B). No files touched.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coal_config import cfg
from memory.embed import ensure_ollama

PORT_RE = re.compile(
    r"\b(input|output|inout)\s+(?:wire|reg|logic)?\s*"
    r"(\[[^\]]+\])?\s*([A-Za-z_][A-Za-z0-9_]*)", re.I)


def hdl_fix(text):
    """Mechanical HDL guardrails for model-generated Verilog:
      - drop blank lines and comment-only lines (kills commentary bloat)
      - move reg/wire/integer/logic declarations that appear INSIDE a
        procedural block (always/initial) up to module scope (a decl after
        a statement is a syntax error), and drop ones that duplicate a
        module-scope declaration.
    Returns the cleaned text."""
    lines = [l for l in (text or "").splitlines()
             if l.strip() and not l.strip().startswith("//")]
    first_proc = None
    for i, l in enumerate(lines):
        if re.search(r"\b(always|initial)\b", l):
            first_proc = i
            break
    if first_proc is None:
        return "\n".join(lines)
    decl_re = re.compile(r"^\s*(reg|wire|integer|logic|real|genvar)\b.*;")
    name_re = re.compile(r"^\s*(?:reg|wire|integer|logic|real|genvar)\b"
                         r"(?:\s*\[[^\]]*\])?\s*([A-Za-z_]\w*)")

    def names(line):
        m = name_re.match(line)
        return [m.group(1)] if m else []

    top_names = set()
    for l in lines[:first_proc]:
        if decl_re.match(l):
            top_names.update(names(l))
    hoisted, kept = [], []
    for i, l in enumerate(lines):
        if i > first_proc and decl_re.match(l):
            ns = names(l)
            if ns and all(n in top_names for n in ns):
                continue  # already declared at module scope -> drop dup
            hoisted.append(l.strip())
            top_names.update(ns)
        else:
            kept.append(l)
    if not hoisted:
        return "\n".join(kept)
    return "\n".join(kept[:first_proc] + hoisted + kept[first_proc:])


class ChipArchitect:
    def __init__(self, model=None, url=None):
        b = cfg.get("chip", {}) or {}
        self.model = model or b.get("model", "chip-design-ai-v4")
        self.url = (url or b.get("ollama_url")
                    or cfg.memory.ollama_url).rstrip("/")

    def available(self):
        return ensure_ollama()

    def _chat(self, prompt, timeout=240, num_ctx=8192, keep_alive="10m"):
        payload = {"model": self.model,
                   "messages": [{"role": "user", "content": prompt}],
                   "stream": False, "format": "",
                   "keep_alive": keep_alive,
                   "options": {"temperature": 0.2, "num_ctx": num_ctx}}
        req = urllib.request.Request(
            self.url + "/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return ((d.get("message") or {}).get("content") or "").strip()

    # ---- deterministic port parser ----
    @staticmethod
    def extract_ports(module_text):
        """Parse module ports into [{name, dir, width}] (handles
        comma-separated ports like `input [3:0] a, b`)."""
        text = re.sub(r"//.*?$|/\*.*?\*/", "", module_text,
                      flags=re.M | re.S)
        m = re.search(r"\bmodule\s+[A-Za-z_]\w*\s*\((.*?)\)\s*;", text, re.S)
        header = m.group(1) if m else text
        ports, i, n = [], 0, len(header)
        DIR = re.compile(r"\b(input|output|inout)\b")
        TYPE = re.compile(r"\s*(?:wire|reg|logic|signed)?\s*"
                          r"(\[[^\]]+\]\s*)?([A-Za-z_][A-Za-z0-9_]*)")
        CONT = re.compile(r"\s*,\s*(\[[^\]]+\]\s*)?"
                          r"([A-Za-z_][A-Za-z0-9_]*)")
        while i < n:
            dm = DIR.search(header, i)
            if not dm:
                break
            direction = dm.group(1).lower()
            tm = TYPE.match(header, dm.end())
            if not tm:
                i = dm.start() + 1
                continue
            width = tm.group(1).strip() if tm.group(1) else "1"
            name = tm.group(2)
            if name.lower() not in ("module", "begin", "end", "always"):
                ports.append({"name": name, "dir": direction,
                              "width": width})
            j = dm.end() + len(tm.group(0))
            while j < n:
                cm = CONT.match(header, j)
                if not cm:
                    break
                cname = cm.group(2)
                if cname.lower() in ("module", "begin", "end", "always",
                                     "input", "output", "inout"):
                    break
                ports.append({"name": cname, "dir": direction,
                              "width": (cm.group(1).strip() if cm.group(1)
                                        else width)})
                j += len(cm.group(0))
            i = dm.start() + 1
        # dedup
        seen, out = set(), []
        for p in ports:
            if p["name"] not in seen:
                seen.add(p["name"])
                out.append(p)
        return out

    @staticmethod
    def port_line(p):
        return f"{p['dir']} {p.get('width', '1')} {p['name']}"

    @staticmethod
    def extract_module_name(module_text):
        m = re.search(r"\bmodule\s+([A-Za-z_]\w*)", module_text or "")
        return m.group(1) if m else ""

    def contract_text(self, module_text):
        ports = self.extract_ports(module_text)
        return "\n".join(self.port_line(p) for p in ports)

    # ---- model-aided planning / review ----
    def plan_ports(self, description, timeout=240):
        """Ask the model for a concise module port list for a description.
        Returns {'text', 'ports'} where ports is parsed [{name,dir,width}].
        Retries once if the first reply has no parseable ports."""
        base = ("You are an RTL architect. For the module requested below, "
                "output ONLY the Verilog module header on a single line "
                "(or few lines):\n"
                "module NAME( input/out TYPE WIDTH name, ... );\n"
                "List every port with direction, optional width, and name. "
                "Do NOT output any body, always/begin/end, wires, "
                "assignments, or comments.\n\n")
        for attempt in range(2):
            text = self._chat(base + description, timeout=timeout)
            ports = self.extract_ports(text)
            if ports:
                return {"text": text, "ports": ports,
                        "name": self.extract_module_name(text)}
            description = ("(Your previous reply had no `module NAME(...)` "
                           "header. Output ONLY the module header line with "
                           "the full port list.)\n" + description)
        return {"text": text, "ports": []}

    def review(self, rtl, contract, timeout=240):
        """Ask the model to check RTL ports against a contract."""
        prompt = (
            "You are an RTL reviewer. The contract lists the required module "
            "ports. Check the RTL's ports EXACTLY against the contract and "
            "report ONLY the mismatches, one per line, as: "
            "'MISMATCH <port>: contract says X, rtl has Y' or 'OK'.\n\n"
            "CONTRACT:\n" + contract + "\n\nRTL:\n" + rtl[:3000])
        text = self._chat(prompt, timeout=timeout)
        return text

    def verify_contract(self, module_text, expected_ports):
        """Deterministic check: does the module match expected ports?
        expected_ports: list of {name, dir} (width ignored for the match).
        Returns (ok, missing, extra)."""
        got = self.extract_ports(module_text)
        got_by = {p["name"]: p["dir"] for p in got}
        exp = {(p["name"], p["dir"]) for p in expected_ports}
        missing = [p["name"] for p in expected_ports
                   if p["name"] not in got_by]
        extra = [p["name"] for p in got if (p["name"], p["dir"]) not in exp]
        return not missing and not extra, missing, extra


if __name__ == "__main__":
    a = ChipArchitect()
    print("available:", a.available())
    rtl = ("module alu(input [3:0] a, b, input [1:0] op, "
           "output reg [3:0] y, output zero, carry); endmodule")
    print("ports:", a.extract_ports(rtl))
    ok, miss, extra = a.verify_contract(
        rtl, [{"name": "a", "dir": "input"}, {"name": "b", "dir": "input"},
              {"name": "op", "dir": "input"}, {"name": "y", "dir": "output"},
              {"name": "zero", "dir": "output"},
              {"name": "carry", "dir": "output"}])
    print("verify:", ok, miss, extra)