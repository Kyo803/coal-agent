"""Polisher: repolish the finished product (format, lint, tidy).

Runs best-effort formatters/linters in the sandbox; never fails the build.
"""
from __future__ import annotations

from sandbox import sb

POLISH = {
    "python": "python3 -m black . 2>/dev/null || python3 -m autopep8 -ir . "
              "2>/dev/null || true",
    "node": "npx --yes prettier --write \"**/*.{ts,tsx,js,jsx,css,scss,json,"
            "html,md}\" 2>/dev/null || true",
    "react": "npx --yes prettier --write \"**/*.{ts,tsx,js,jsx,css,json,"
             "html,md}\" 2>/dev/null || true",
    "nextjs": "npx --yes prettier --write \"**/*.{ts,tsx,js,jsx,css,json,"
              "html,md}\" 2>/dev/null || true",
    "hdl": "true",
    "rust": "cargo fmt 2>/dev/null || true",
    "go": "gofmt -w . 2>/dev/null || true",
}

LINT = {
    "python": "python3 -m ruff check . 2>/dev/null || true",
    "node": "npx --yes eslint . 2>/dev/null || true",
    "react": "npx --yes eslint . 2>/dev/null || true",
}


def polish(cwd: str, stack: str = "node", timeout: int = 600) -> dict:
    report = {}
    fmt = POLISH.get(stack, "true")
    r = sb.shell(fmt, cwd=cwd, timeout=timeout)
    report["format"] = {"rc": r["rc"]}
    lint = LINT.get(stack)
    if lint:
        r = sb.shell(lint, cwd=cwd, timeout=timeout)
        report["lint"] = {"rc": r["rc"],
                          "out": (r.get("out") or "")[:800]}
    report["ok"] = True  # polishing is best-effort
    return report
