"""Planner: description -> build spec + file manifest."""
from __future__ import annotations

import json
import re

from . import generator

_SYS = (
    "You are Coal's build planner. Return ONLY JSON: "
    '{"files": [{"path": "relative/path", "purpose": "one line"}], '
    '"spec": "overall build spec"} for a small, complete project. Keep it '
    "to 3-8 files."
)

_DEFAULT = {
    "node": [{"path": "package.json", "purpose": "npm manifest + scripts"},
             {"path": "index.html", "purpose": "entry html"},
             {"path": "src/main.js", "purpose": "app entry"},
             {"path": "src/style.css", "purpose": "styles"},
             {"path": "README.md", "purpose": "docs"}],
    "vite": [{"path": "package.json", "purpose": "vite manifest + build"},
             {"path": "index.html", "purpose": "vite entry"},
             {"path": "src/main.ts", "purpose": "app entry"},
             {"path": "src/style.css", "purpose": "styles"}],
    "python": [{"path": "main.py", "purpose": "entry"},
               {"path": "README.md", "purpose": "docs"}],
    "hdl": [{"path": "top.v", "purpose": "top module"},
            {"path": "tb_top.v", "purpose": "testbench"}],
}


def plan(description: str, stack: str = "node",
         llm_ok: bool | None = None) -> dict:
    if llm_ok is None:
        try:
            llm_ok = generator.available()
        except Exception:
            llm_ok = False
    manifest, spec = [], description
    if llm_ok:
        text = generator._chat(
            [{"role": "system", "content": _SYS},
             {"role": "user", "content": f"STACK: {stack}\n\n{description[:1500]}"}],
            max_tokens=900, temperature=0.2)
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
                manifest = [f for f in data.get("files", [])
                            if isinstance(f, dict) and f.get("path")]
                spec = data.get("spec", description)
            except Exception:
                manifest = []
    if not manifest:
        manifest = _DEFAULT.get(stack, _DEFAULT["node"])
    return {"description": description, "stack": stack,
            "manifest": manifest, "spec": spec}
