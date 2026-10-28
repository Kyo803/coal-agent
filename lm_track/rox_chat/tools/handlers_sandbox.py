"""Sandbox tool handlers — run anything inside the isolated Ubuntu (WSL2).

The sandbox has root (NOPASSWD sudo), the internet, and a full toolchain;
the Windows host is sealed off. These handlers are the bridge.
"""
from __future__ import annotations

import os

from sandbox import sb
from .handlers_fs import _resolve


def _fmt(r: dict) -> str:
    out = (r.get("out") or "") + (r.get("err") or "")
    return out.strip() or f"(no output, rc={r.get('rc')})"


def sandbox_run(args, ctx):
    cmd = args.get("command") or args.get("cmd") or ""
    if not cmd:
        return {"ok": False, "output": "command required"}
    timeout = int(args.get("timeout") or 300)
    r = sb.shell(cmd, timeout=timeout, root=bool(args.get("root")),
                 cwd=args.get("cwd"))
    ok = r["rc"] == 0
    return {"ok": ok, "output": f"$ {cmd}\n{_fmt(r)}\n(rc={r['rc']})"}


def sandbox_write(args, ctx):
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    content = args.get("content", "")
    ok = sb.write(path, content, root=bool(args.get("root")))
    return {"ok": ok, "output": f"wrote {len(content)} bytes -> {path}"
            if ok else f"write failed: {path}"}


def sandbox_read(args, ctx):
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    text = sb.read_text(path)
    if text is None or text == "":
        exists = sb.exists(path)
        if not exists:
            return {"ok": False, "output": f"not found: {path}"}
    return {"ok": True, "output": text}


def sandbox_edit(args, ctx):
    path = args.get("path")
    old = args.get("old")
    new = args.get("new")
    if not (path and old is not None and new is not None):
        return {"ok": False, "output": "path, old, new required"}
    content = sb.read_text(path)
    if old not in content:
        return {"ok": False, "output": "old string not found"}
    ok = sb.write(path, content.replace(old, new, 1))
    return {"ok": ok, "output": f"edited {path}" if ok else "edit failed"}


def sandbox_list(args, ctx):
    return {"ok": True, "output": sb.listdir(args.get("path", "."))}


def sandbox_move(args, ctx):
    src, dst = args.get("source"), args.get("destination")
    if not (src and dst):
        return {"ok": False, "output": "source, destination required"}
    ok = sb.move(src, dst)
    return {"ok": ok, "output": f"moved {src} -> {dst}" if ok else "move failed"}


def sandbox_delete(args, ctx):
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    ok = sb.remove(path, recursive=bool(args.get("recursive")))
    return {"ok": ok, "output": f"deleted {path}" if ok else "delete failed"}


def sandbox_pkg(args, ctx):
    manager = (args.get("manager") or "apt").lower()
    packages = args.get("packages") or args.get("package")
    if not packages:
        return {"ok": False, "output": "packages required"}
    if manager == "apt":
        r = sb.apt(packages, update=True,
                   timeout=int(args.get("timeout") or 1800))
    elif manager in ("pip", "pip3"):
        r = sb.pip(packages, timeout=int(args.get("timeout") or 1200))
    elif manager in ("npm",):
        r = sb.npm(packages, global_=bool(args.get("global")),
                   timeout=int(args.get("timeout") or 1200))
    else:
        return {"ok": False, "output": f"unknown manager: {manager}"}
    return {"ok": r.get("rc", 1) == 0,
            "output": f"[{manager}] {packages}\n{_fmt(r)}"}


def sandbox_toolchain(args, ctx):
    stack = args.get("stack")
    if not stack or stack == "all":
        return {"ok": True, "output": str(sb.toolchains())}
    if stack == "list":
        return {"ok": True, "output": str(sb.toolchains())}
    r = sb.install_toolchain(stack)
    return {"ok": r.get("rc", 1) == 0,
            "output": f"toolchain '{stack}':\n{_fmt(r)}"}


def sandbox_info(args, ctx):
    snap = sb.snapshot()
    vers = "\n".join(f"  {k}: {v}" for k, v in snap["versions"].items())
    return {"ok": True,
            "output": f"{snap['info']}\nfree_ram_mb: {snap['free_ram_mb']}\n"
                      f"tools:\n{vers}"}


def sandbox_upload(args, ctx):
    host = _resolve(args.get("host_path") or args.get("path") or "", ctx)
    dest = args.get("sandbox_path") or args.get("destination") or (
        "/home/rox/shared/" + os.path.basename(host))
    if not os.path.exists(host):
        return {"ok": False, "output": f"host file not found: {host}"}
    with open(host, "rb") as f:
        data = f.read()
    ok = sb.write(dest, data)
    return {"ok": ok, "output": f"uploaded {host} -> {dest} ({len(data)} b)"
            if ok else "upload failed"}


def sandbox_download(args, ctx):
    src = args.get("sandbox_path") or args.get("path")
    host = _resolve(args.get("host_path") or args.get("destination") or
                    (os.path.join(ctx.workspace,
                                  os.path.basename(src or "download"))), ctx)
    data = sb.read(src, binary=True) if src else None
    if data is None:
        return {"ok": False, "output": f"sandbox file not found: {src}"}
    os.makedirs(os.path.dirname(host), exist_ok=True)
    with open(host, "wb") as f:
        f.write(data)
    return {"ok": True, "output": f"downloaded {src} -> {host} ({len(data)} b)"}
