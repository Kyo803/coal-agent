"""Compiler: build a project inside the isolated sandbox (real feedback)."""
from __future__ import annotations

from sandbox import sb

STACKS = {
    "node": "npm install --no-audit --no-fund && npm run build",
    "vite": "npm install --no-audit --no-fund && npm run build",
    "react": "npm install --no-audit --no-fund && npm run build",
    "nextjs": "npm install --no-audit --no-fund && npm run build",
    "typescript": "npx tsc --noEmit",
    "python": "python3 -m compileall -q .",
    "hdl": "iverilog -g2012 -o /tmp/rox_build.out *.v",
    "rust": "cargo build --quiet",
    "go": "go build ./...",
    "cpp": "make",
}

_MARKERS = {
    "package.json": "node",
    "tsconfig.json": "typescript",
    "cargo.toml": "rust",
    "go.mod": "go",
    "makefile": "cpp",
}


def detect_stack(cwd: str) -> str:
    r = sb.shell(f"ls -1 {cwd!r} 2>/dev/null", timeout=30)
    names = {ln.strip().lower() for ln in (r.get("out") or "").splitlines()}
    for marker, stack in _MARKERS.items():
        if marker in names:
            return stack
    if any(n.endswith(".v") for n in names):
        return "hdl"
    if any(n.endswith(".py") for n in names):
        return "python"
    return "node"


def available(stack: str) -> bool:
    tool = {"node": "node", "nextjs": "node", "go": "go",
            "rust": "cargo", "hdl": "iverilog", "python": "python3"}.get(
        stack, "node")
    return bool(sb.which(tool))


def compile(cwd: str, stack: str | None = None, timeout: int = 1200) -> dict:
    stack = stack or detect_stack(cwd)
    cmd = STACKS.get(stack, STACKS["node"])
    r = sb.shell(cmd, cwd=cwd, timeout=timeout)
    return {"ok": r["rc"] == 0, "rc": r["rc"], "out": r.get("out", ""),
            "err": r.get("err", ""), "stack": stack, "command": cmd,
            "cwd": cwd}
