"""Safe shell runner — the only path free-text commands execute through.

  from tools.shell import run_safe
  result = run_safe("git status", workspace="~/.coal/work",
                    ask_callback=confirm_fn)

Flow: gate() -> verdict
  allow (T0/T1) -> run
  ask   (T2)    -> ask_callback("y"/"n"); y -> run, n -> declined
  deny  (T3)    -> refuse, NEVER run

Execution is in the user's shell (cmd or PowerShell) but ONLY after the
gate approves. Result is capped and includes the gate verdict.
"""
from __future__ import annotations

import os
import subprocess
import sys

try:
    from .shell_gate import gate
except ImportError:  # running as a standalone script
    from shell_gate import gate

MAX_OUT = 6000
DEFAULT_TIMEOUT = 90


def _run_process(command, cwd, timeout):
    # Prefer list-form with the system shell to avoid stray escaping.
    # On Windows we run through cmd.exe so `&`, `|`, `&&` behave normally,
    # but ONLY because the gate already validated every primitive.
    shell = os.name == "nt"
    try:
        r = subprocess.run(
            command, shell=shell, capture_output=True, text=True,
            timeout=timeout, cwd=cwd or None,
            encoding="utf-8", errors="replace")
        out = (r.stdout or "")[-MAX_OUT:] + (r.stderr or "")[-2000:]
        if len(out) > MAX_OUT:
            out = out[-MAX_OUT:]
        return {"ok": r.returncode == 0, "exit": r.returncode,
                "output": out.strip() or f"(no output, exit={r.returncode})"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit": -1,
                "output": f"command timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "exit": -1, "output": f"exec failed: {e}"}


def run_safe(command, workspace=None, ask_callback=None, timeout=None,
             cwd=None):
    """Gate then run. Returns dict with 'verdict' reflecting the gate."""
    cmd = command or ""
    g = gate(cmd, workspace=workspace)
    verdict = g["verdict"]
    if verdict == "deny":
        return {"ok": False, "verdict": "deny", "tier": g["tier"],
                "output": f"BLOCKED (Tier {g['tier']}): {g['reason']}. "
                          "This command is not allowed."}
    if verdict == "ask":
        if ask_callback is None:
            return {"ok": False, "verdict": "ask", "tier": 2,
                    "output": f"needs approval: {g['reason']}"}
        ans = ask_callback(f"[Coal] Run this (Tier 2)? {cmd} [y/n]: ")
        if not str(ans).strip().lower() in ("y", "yes", "ok"):
            return {"ok": False, "verdict": "ask", "tier": 2,
                    "output": "user declined the command."}

    eff_cwd = cwd or workspace or os.getcwd()
    res = _run_process(cmd, eff_cwd, timeout or DEFAULT_TIMEOUT)
    res["verdict"] = "allow"
    res["tier"] = g["tier"]
    res["command"] = cmd
    return res


def run_safe_list(commands, workspace=None, ask_callback=None):
    """Run several commands, each gated independently. Stops on failure."""
    out = []
    for c in commands:
        r = run_safe(c, workspace=workspace, ask_callback=ask_callback)
        out.append(f"$ {c}\n  -> {r.get('output','')[:500]}")
        if not r.get("ok"):
            break
    return {"ok": True, "output": "\n".join(out)}


if __name__ == "__main__":
    for cmd in ["git status", "del notes.txt", "format c:",
                "type shell_gate.py | Select-Object -First 2",
                "python -c \"print('hi')\""]:
        r = run_safe(cmd, workspace=r"C:\Users\WERU1\.coal\work",
                     ask_callback=lambda q: "y")
        print(f"{cmd[:34]:36s} -> verdict={r.get('verdict')} ok={r.get('ok')} "
              f"tier={r.get('tier')} out={r.get('output','')[:60]!r}")