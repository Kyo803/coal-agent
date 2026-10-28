"""Port introspection for Verilog modules.

Composition needs to know, for every block, what ports exist, their
direction, and their width. Rather than duplicating that knowledge in a
table that can drift, we parse it out of the RTL that the generators just
emitted -- the single source of truth.

    ports_of(rtl, "uart_tx")
    -> {"clk":  {"dir": "input",  "width": 1, "type": "wire"},
        "data": {"dir": "input",  "width": 8, "type": "wire"},
        "tx":   {"dir": "output", "width": 1, "type": "reg"}, ...}

Handles the forms the generators produce:
    input  wire       clk
    input  wire [7:0] data
    output reg  [3:0] q
    input  wire [3:0] a, b          (shared declaration)
    output wire [7:0] y, z
"""
from __future__ import annotations

import re

_DIRS = ("input", "output", "inout")
_TYPES = ("wire", "reg", "logic")
_RANGE = re.compile(r"\[\s*(-?\d+)\s*:\s*(-?\d+)\s*\]")
_IDENT = re.compile(r"[A-Za-z_]\w*")


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    return text


def _match_paren(text: str, start: int) -> int:
    """Index just past the ')' matching the '(' at `start`."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def module_header(text: str, top: str | None = None) -> tuple[str, str] | None:
    """Return (module_name, port_list_text) for the requested module."""
    text = _strip_comments(text)
    for m in re.finditer(r"\bmodule\s+([A-Za-z_]\w*)", text):
        name = m.group(1)
        if top and name != top:
            continue
        i = m.end()
        # skip an optional parameter list:  #( ... )
        while i < len(text) and text[i].isspace():
            i += 1
        if i < len(text) and text[i] == "#":
            j = text.find("(", i)
            if j < 0:
                continue
            i = _match_paren(text, j)
            if i < 0:
                continue
            while i < len(text) and text[i].isspace():
                i += 1
        if i < len(text) and text[i] == "(":
            end = _match_paren(text, i)
            if end < 0:
                continue
            return name, text[i + 1:end - 1]
    return None


def _split_ports(body: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return parts


def _parse_one(tok: str, inherit: dict | None) -> tuple[str, dict] | None:
    tok = " ".join(tok.split())
    if not tok:
        return None
    low = tok.lower()
    spec = dict(inherit) if inherit else {"dir": None, "type": "wire",
                                          "width": 1}
    for d in _DIRS:
        if re.search(rf"\b{d}\b", low):
            spec["dir"] = d
            break
    for t in _TYPES:
        if re.search(rf"\b{t}\b", low):
            spec["type"] = t
            break
    rng = _RANGE.search(tok)
    if rng:
        a, b = int(rng.group(1)), int(rng.group(2))
        spec["width"] = abs(a - b) + 1
        tok = tok[:rng.start()] + " " + tok[rng.end():]
    elif inherit and spec.get("dir") is not None:
        # a fresh declaration without a range is scalar
        spec["width"] = 1
    names = _IDENT.findall(tok)
    names = [n for n in names
             if n.lower() not in _DIRS + _TYPES + ("signed", "unsigned")]
    if not names:
        return None
    return names[-1], {
        "dir": spec.get("dir"),
        "width": int(spec.get("width") or 1),
        "type": spec.get("type") or "wire",
    }


def ports_of(rtl: str, top: str | None = None) -> dict:
    """Ordered {port: {dir, width, type}} parsed from the module header."""
    hdr = module_header(rtl, top)
    if not hdr:
        return {}
    _name, body = hdr
    out: dict[str, dict] = {}
    spec = None
    for tok in _split_ports(body):
        parsed = _parse_one(tok, spec)
        if not parsed:
            continue
        name, info = parsed
        # remember the declaration for the next comma-separated names
        if info["dir"] is not None:
            spec = {"dir": info["dir"], "type": info["type"],
                    "width": info["width"]}
        if info["dir"] is None and spec:
            info["dir"] = spec["dir"]
            info["type"] = spec["type"]
        out[name] = info
    return out


def module_name(rtl: str, top: str | None = None) -> str | None:
    hdr = module_header(rtl, top)
    return hdr[0] if hdr else None


def summary(ports: dict) -> str:
    bits = []
    for name, p in ports.items():
        w = "" if p["width"] == 1 else f"[{p['width'] - 1}:0] "
        bits.append(f"{p['dir'][:3]} {w}{name}")
    return ", ".join(bits)
