"""Build helpers: toolchain setup + autonomous project builder.

  setup_toolchain  -> install the packages a stack needs (npm/winget/pip)
  build_project    -> one prompt drives plan -> write files -> audit ->
                      repair -> verify (the autonomous builder)

The builder uses the project layer (journal/audit/context) and the write
path so ROX N can build whole multi-file projects on its own.
"""
from __future__ import annotations

import os
import subprocess
import sys

from rox_config import cfg

CREATE_NO_WINDOW = 0x08000000

STACKS = {
    "web": {
        "dev": ["typescript", "vite", "@vitejs/plugin-react",
                "@types/react", "@types/react-dom", "tailwindcss",
                "postcss", "autoprefixer"],
        "prod": ["react", "react-dom"],
    },
    "react": {
        "dev": ["typescript", "vite", "@vitejs/plugin-react",
                "@types/react", "@types/react-dom", "tailwindcss",
                "postcss", "autoprefixer"],
        "prod": ["react", "react-dom"],
    },
    "node": {"dev": ["typescript", "@types/node"], "prod": []},
    "python": {"dev": ["pytest"], "prod": []},
    "hdl": {"winget": ["Icarus.Verilog"]},
}

WINGET = ("winget install --id {id} -e --silent "
          "--accept-source-agreements --accept-package-agreements")


def _run(cmd, cwd, timeout=900):
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd,
                           capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace",
                           creationflags=CREATE_NO_WINDOW)
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or ""))[-1500:]
    except subprocess.TimeoutExpired:
        return False, f"timed out: {cmd}"
    except Exception as e:
        return False, f"failed: {e}"


def setup_toolchain(args, ctx):
    """Install the packages a stack needs.
      args: stack (web|react|node|python|hdl), dir (project dir),
            prod (bool, also install prod deps)"""
    stack = (args.get("stack") or "web").lower()
    spec = STACKS.get(stack)
    if not spec:
        return {"ok": False,
                "output": f"unknown stack '{stack}'. Options: "
                          + ", ".join(STACKS)}
    cwd = os.path.abspath(os.path.expanduser(
        args.get("dir") or getattr(ctx, "workspace", "~/.rox/work")
        or "~/.rox/work"))
    log = []

    if "winget" in spec:
        for pkg in spec["winget"]:
            ok, out = _run(WINGET.format(id=pkg), cwd)
            log.append(f"winget {pkg}: {'OK' if ok else 'FAIL'} "
                       f"{out.strip()[-120:]}")

    if "dev" in spec or "prod" in spec:
        if not os.path.exists(os.path.join(cwd, "package.json")):
            _run("npm init -y", cwd)
        devs = spec.get("dev", [])
        if devs:
            ok, out = _run("npm install -D " + " ".join(devs), cwd)
            log.append(f"npm -D ({len(devs)} pkgs): {'OK' if ok else 'FAIL'} "
                       f"{out.strip()[-120:]}")
        prods = spec.get("prod", [])
        if args.get("prod") and prods:
            ok, out = _run("npm install " + " ".join(prods), cwd)
            log.append(f"npm prod ({len(prods)}): {'OK' if ok else 'FAIL'} "
                       f"{out.strip()[-120:]}")

    return {"ok": all("OK" in l or "FAIL" not in l for l in log) and bool(log),
            "output": f"toolchain '{stack}' in {cwd}:\n" + "\n".join(log)}


if __name__ == "__main__":
    from types import SimpleNamespace
    ctx = SimpleNamespace(workspace="~/.rox/work")
    print(setup_toolchain({"stack": "web", "dir": os.path.expanduser(
        "~/.rox/work")}, ctx))