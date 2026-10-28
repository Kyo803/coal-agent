"""Toolchain stacks: detect + install language/framework support."""
from __future__ import annotations

from . import base, exec as bexec, pkg

# name -> {check, apt, extra}
STACKS = {
    "node": {"check": "node --version && npm --version", "apt": []},
    "web": {"check": "node --version && npm --version",
            "apt": [],
            "extra": "corepack enable >/dev/null 2>&1; "
                     "npm install -g pnpm >/dev/null 2>&1 || true"},
    "python": {"check": "python3 --version && pip3 --version",
               "apt": ["python3", "python3-pip", "python3-venv",
                       "python3-dev"]},
    "cpp": {"check": "gcc --version && g++ --version && make --version",
            "apt": ["build-essential", "gcc", "g++", "make", "cmake",
                    "pkg-config", "clang"]},
    "hdl": {"check": "iverilog -V && verilator --version",
            "apt": ["iverilog", "verilator", "gtkwave"]},
    "go": {"check": "go version", "apt": ["golang-go"]},
    "rust": {"check": "cargo --version", "apt": [],
             "extra": "if ! command -v cargo >/dev/null 2>&1; then "
                      "curl --proto '=https' --tlsv1.2 -sSf "
                      "https://sh.rustup.rs | sh -s -- -y; fi"},
    "db": {"check": "sqlite3 --version", "apt": ["sqlite3"]},
    "tools": {"check": "git --version && jq --version && rg --version",
              "apt": ["git", "curl", "wget", "unzip", "zip", "jq",
                      "ripgrep", "tree", "tmux", "htop"]},
}


def detect(name: str) -> bool:
    s = STACKS.get(name)
    if not s:
        return False
    return bexec.ok(s["check"], timeout=60)


def available() -> dict:
    return {name: detect(name) for name in STACKS}


def install(name: str, timeout: int = 2400) -> dict:
    s = STACKS.get(name)
    if not s:
        return {"rc": 1, "out": "", "err": f"unknown stack: {name}"}
    log = []
    if s.get("apt"):
        r = pkg.apt_install(s["apt"], update=True, timeout=timeout)
        log.append(f"apt: rc={r['rc']}")
    if s.get("extra"):
        r = base.run(s["extra"], timeout=timeout)
        log.append(f"extra: rc={r['rc']}")
    okd = detect(name)
    return {"rc": 0 if okd else 1, "out": "\n".join(log),
            "err": "" if okd else "install finished but check failed"}


def install_many(names, timeout: int = 3600) -> dict:
    out = {}
    for n in names:
        out[n] = install(n, timeout=timeout)
    return out
