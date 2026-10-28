"""Tester: run a project's tests inside the sandbox."""
from __future__ import annotations

from sandbox import sb

TEST_CMDS = {
    "node": "npm test --silent",
    "vite": "npm test --silent",
    "react": "npm test --silent",
    "nextjs": "npm test --silent",
    "python": "python3 -m pytest -q",
    # all .v compiled once; vvp runs the root module (the testbench, since
    # it instantiates the DUT). No duplicate testbench args.
    "hdl": "iverilog -g2012 -o /tmp/rox_tb.out *.v && vvp /tmp/rox_tb.out",
    "rust": "cargo test --quiet",
    "go": "go test ./...",
}


def run(cwd: str, stack: str = "node", command: str | None = None,
        timeout: int = 1200) -> dict:
    cmd = command or TEST_CMDS.get(stack, TEST_CMDS["node"])
    if command is None and stack == "python":
        probe = sb.shell("ls test_*.py tests/test_*.py 2>/dev/null",
                         cwd=cwd, timeout=30)
        if not (probe.get("out") or "").strip():
            return {"ok": True, "skipped": True, "rc": 0,
                    "out": "(no tests found — smoke only)", "err": "",
                    "command": cmd, "cwd": cwd}
    r = sb.shell(cmd, cwd=cwd, timeout=timeout)
    return {"ok": r["rc"] == 0, "rc": r["rc"], "out": r.get("out", ""),
            "err": r.get("err", ""), "command": cmd, "cwd": cwd}


def smoke(cwd: str, stack: str = "node") -> dict:
    """A cheap 'does it load' check when there are no formal tests."""
    cmd = {"python": "python3 -c 'import compileall,sys; "
                     "sys.exit(0 if compileall.compile_dir(\".\", quiet=1) "
                     "else 1)'",
           "node": "[ -f package.json ] && node -e \"require('./package.json')\"",
           "hdl": "iverilog -g2012 -o /tmp/rox_smoke.out *.v",
           }.get(stack, "true")
    r = sb.shell(cmd, cwd=cwd, timeout=600)
    return {"ok": r["rc"] == 0, "rc": r["rc"], "out": r.get("out", ""),
            "err": r.get("err", ""), "command": cmd}
