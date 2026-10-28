"""Diagnoser: turn raw compiler/test output into a structured diagnosis.

Classes: syntax, type, interface, test_failure, runtime, dependency,
unknown. Extracts file/line when present.
"""
from __future__ import annotations

import re

_PATTERNS = [
    ("type", re.compile(r"([\w./\\-]+\.tsx?)\((\d+),(\d+)\): error TS(\d+)")),
    ("syntax", re.compile(r"([\w./\\-]+\.v):(\d+):\s*(error)")),
    ("syntax", re.compile(r'File "([^"]+)", line (\d+)')),
    ("dependency", re.compile(r"npm ERR!|Cannot find module|"
                              r"ModuleNotFoundError|No module named")),
    ("test_failure", re.compile(r"AssertionError|FAILED|tests? failed|"
                                r"^\s*FAIL\b", re.M)),
    ("runtime", re.compile(r"Traceback \(most recent call last\)|"
                           r"[A-Za-z_.]+Error:|Exception")),
]


def classify(output: str, language: str | None = None) -> dict:
    o = output or ""
    cls, file, line, msg = "unknown", None, None, ""
    for name, rx in _PATTERNS:
        m = rx.search(o)
        if m:
            cls = name
            g = m.groups()
            if g and g[0]:
                file = g[0]
            for x in g[1:]:
                if x and x.isdigit():
                    line = int(x)
                    break
            # refine syntax vs error for python
            if name == "runtime" and "SyntaxError" in o:
                cls = "syntax"
            break
    # first non-empty error-ish line as the message
    for ln in o.splitlines():
        s = ln.strip()
        if s and ("error" in s.lower() or "Error" in s or "ERR" in s):
            msg = s[:300]
            break
    if not msg:
        msg = (o.strip().splitlines() or [""])[-1][:300]
    return {"class": cls, "file": file, "line": line, "message": msg,
            "language": language}


def is_error(output: str) -> bool:
    return classify(output)["class"] != "unknown"
