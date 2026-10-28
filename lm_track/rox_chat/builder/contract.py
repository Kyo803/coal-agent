"""Interface contract: what each unit exports/imports, so units can be
frozen and interface drift caught before it cascades.

Language-agnostic: works for TS/JS (export/import) and Python (def/class).
"""
from __future__ import annotations

import json
import re

_TS_EXPORT = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function|const|let|var|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
    re.M)
_JS_EXPORT = re.compile(
    r"^\s*module\.exports\s*=|^\s*exports\.([A-Za-z_$][\w$]*)", re.M)
_PY_DEF = re.compile(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)", re.M)
_TS_IMPORT = re.compile(r"^\s*import\s+.*?from\s+['\"]([^'\"]+)['\"]", re.M)
_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))",
                        re.M)


def infer_exports(source: str, language: str = "ts") -> list:
    if language in ("ts", "tsx", "js", "jsx"):
        names = _TS_EXPORT.findall(source) + \
            [m for m in _JS_EXPORT.findall(source) if m]
        return sorted(set(names))
    if language in ("py", "python"):
        # top-level defs/classes only (no indentation)
        return sorted({m.group(1) for m in _PY_DEF.finditer(source)
                       if not m.group(0).startswith((" ", "\t"))})
    return []


def infer_imports(source: str, language: str = "ts") -> list:
    if language in ("ts", "tsx", "js", "jsx"):
        return sorted(set(_TS_IMPORT.findall(source)))
    if language in ("py", "python"):
        out = {a or b for a, b in _PY_IMPORT.findall(source)}
        return sorted(x for x in out if x)
    return []


class Contract:
    def __init__(self, data: dict | None = None):
        self.units = (data or {}).get("units", {})

    def set_unit(self, rel: str, exports=None, imports=None, kind=None):
        self.units[rel] = {"exports": sorted(set(exports or [])),
                           "imports": sorted(set(imports or [])),
                           "kind": kind or ""}

    def get(self, rel: str) -> dict:
        return self.units.get(rel, {})

    def all(self) -> dict:
        return self.units

    def check_missing(self, rel: str, needed: list) -> list:
        have = set(self.get(rel).get("exports", []))
        return [n for n in needed if n not in have]

    def to_dict(self) -> dict:
        return {"units": self.units}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=1)

    @classmethod
    def from_json(cls, text: str):
        try:
            return cls(json.loads(text))
        except Exception:
            return cls()
