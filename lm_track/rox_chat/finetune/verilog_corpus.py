"""Verilog SFT corpus: turn every gated/verified RTL unit into a clean
(prompt -> file) training pair for the QLoRA'd Verilog drafter.

Reads mission specs + sandbox files; only accepted missions (checkpoint
`accept` true) are mined, so the corpus is trustworthy RTL.
"""
from __future__ import annotations

import json
import posixpath

from builder import checkpoints as CK
from builder import missions as M
from sandbox import sb

_SYS = ("You are ROX N writing a single Verilog module that EXACTLY matches "
        "the declared port list and purpose. Output ONLY the code.")


def export(path: str | None = None, min_accept: bool = True) -> dict:
    rows = []
    for name in M.all_names():
        spec = M.load(name)
        if not spec or spec.get("stack") != "hdl":
            continue
        st = CK.load("mission_" + name)
        if min_accept and not (st.get("accept") or st.get("tested")):
            continue
        cwd = M.workspace_dir(name)
        for u in spec.get("manifest", []):
            rel = u.get("path")
            if not (rel or "").endswith(".v"):
                continue
            code = sb.read_text(posixpath.join(cwd, rel))
            if not code:
                continue
            user = (f"{rel}\nPORTS: {u.get('ports', '')}\n"
                    f"PURPOSE: {u.get('purpose', '')}")
            rows.append({"messages": [
                {"role": "system", "content": _SYS},
                {"role": "user", "content": user},
                {"role": "assistant", "content": code},
            ]})
    out = path
    if not out:
        from . import dataset
        out = posixpath.join(dataset.dir(), "verilog_corpus.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"count": len(rows), "path": out}