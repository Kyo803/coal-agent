"""Acceptance: does the built product meet the desired outcome?

Criteria are simple machine-checkable specs:
  "file:dist/index.html"   -> path exists
  "contains:XXX"           -> source/metadata contains the token
  "runs:<command>"         -> command exits 0 in the sandbox
Anything else is reported as not machine-checkable (human/model judges).
"""
from __future__ import annotations

from sandbox import sb


def check(cwd: str, criteria: list) -> dict:
    results = []
    for c in criteria or []:
        c = str(c)
        if c.startswith("file:"):
            p = c.split(":", 1)[1].strip()
            ok = sb.shell(f"test -e {p!r}", timeout=20)["rc"] == 0
            results.append({"criterion": c, "ok": ok})
        elif c.startswith("contains:"):
            tok = c.split(":", 1)[1].strip()
            r = sb.shell(f"grep -rIl {tok!r} . 2>/dev/null | head -1",
                         cwd=cwd, timeout=60)
            results.append({"criterion": c, "ok": bool(r.get("out", "").strip())})
        elif c.startswith("runs:"):
            cmd = c.split(":", 1)[1].strip()
            r = sb.shell(cmd, cwd=cwd, timeout=600)
            results.append({"criterion": c, "ok": r["rc"] == 0})
        else:
            results.append({"criterion": c, "ok": None,
                            "note": "not machine-checkable"})
    machine = [r for r in results if r["ok"] is not None]
    ok = all(r["ok"] for r in machine) if machine else None
    return {"ok": ok, "results": results,
            "unchecked": sum(1 for r in results if r["ok"] is None)}
