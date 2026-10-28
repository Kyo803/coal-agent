"""Artifact / acceptance verification (post-build)."""
from __future__ import annotations

import posixpath

from sandbox import sb

ARTIFACTS = {
    "node": ["dist/index.html", "build/index.html"],
    "vite": ["dist/index.html"],
    "react": ["dist/index.html", "build/index.html"],
    "nextjs": [".next/BUILD_ID"],
    "python": [],
    "hdl": [],
}


def build_outputs(cwd: str, stack: str = "node") -> dict:
    cands = ARTIFACTS.get(stack, ARTIFACTS["node"])
    found = []
    for a in cands:
        p = posixpath.join(cwd, a)
        if sb.shell(f"test -e {p!r}", timeout=20)["rc"] == 0:
            found.append(a)
    return {"present": found, "ok": True if not cands else bool(found)}


def screenshot(cwd: str, out: str, timeout: int = 120) -> dict:
    """Best-effort page screenshot using playwright in the sandbox."""
    script = (
        f"python3 - <<'PY'\n"
        f"import asyncio\n"
        f"async def main():\n"
        f"    from playwright.async_api import async_playwright\n"
        f"    async with async_playwright() as p:\n"
        f"        b = await p.chromium.launch()\n"
        f"        pg = await b.new_page()\n"
        f"        await pg.goto('file://{cwd}/dist/index.html')\n"
        f"        await pg.screenshot(path='{out}', full_page=True)\n"
        f"        await b.close()\n"
        f"asyncio.run(main())\n"
        f"PY")
    r = sb.shell(script, timeout=timeout)
    return {"ok": r["rc"] == 0, "out": r.get("out", ""),
            "err": r.get("err", ""), "path": out}
