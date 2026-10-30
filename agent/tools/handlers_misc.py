"""Categories 11, 12, 13: orchestration, output/delivery, system admin.
"""
from __future__ import annotations

import datetime
import os
import subprocess


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ================= 11. orchestration =================
def todo_write(args, ctx):
    ctx.todos = args.get("items") or []
    return {"ok": True, "output": f"todo list set ({len(ctx.todos)} items)"}


def todo_read(args, ctx):
    if not getattr(ctx, "todos", None):
        return {"ok": True, "output": "(no todos)"}
    return {"ok": True,
            "output": "\n".join(f"- {t}" for t in ctx.todos)}


def ask_user(args, ctx):
    q = args.get("question", "")
    if ctx.ask_callback:
        ans = ctx.ask_callback(q)
        return {"ok": True, "output": f"user answered: {ans}"}
    return {"ok": False, "output": f"no interactive session; question: {q}"}


def notify_user(args, ctx):
    msg = args.get("message", "")
    if ctx.notify_callback:
        ctx.notify_callback(msg)
    return {"ok": True, "output": f"notified user: {msg[:200]}"}


def sleep(args, ctx):
    import time
    time.sleep(min(float(args.get("seconds", 1)), 30))
    return {"ok": True, "output": f"slept {args.get('seconds', 1)}s"}


def schedule_task(args, ctx):
    name = args.get("name", "task")
    delay = args.get("delay", 0)
    ctx.scheduled.append({"name": name, "delay": delay, "at": _now()})
    return {"ok": True, "output": f"scheduled {name} (+{delay}s)"}


def mcp_list_tools(args, ctx):
    tools = getattr(ctx, "mcp_tools", None)
    if not tools:
        return {"ok": False,
                "output": "no MCP servers connected. Use mcp_connect_server "
                          "with a config (e.g. stripe, github) first."}
    return {"ok": True, "output": "\n".join(tools)}


def mcp_connect_server(args, ctx):
    name = args.get("server", args.get("name", ""))
    if name in ("stripe", "slack", "jira", "github", "notion", "linear"):
        return {"ok": True,
                "output": f"MCP server '{name}' requires its connector "
                          "package + credentials. Not installed. Cloud "
                          "tools are gated by default (tools.allow_tier2)."}
    return {"ok": False, "output": f"unknown MCP server: {name}"}


def mcp_call_tool(args, ctx):
    return {"ok": False,
            "output": "no connected MCP server for "
                      f"{args.get('tool', '')}"}


# ================= 12. output / delivery =================
def present_files(args, ctx):
    paths = args.get("paths") or []
    return {"ok": True, "output": "presenting:\n" + "\n".join(paths)}


def export_zip(args, ctx):
    from handlers_fs import zip_files
    src = args.get("source", ctx.workspace or ".")
    dst = args.get("destination", os.path.join(
        ctx.workspace or ".", "export.zip"))
    return zip_files({"source": src, "destination": dst}, ctx)


def render_markdown(args, ctx):
    return {"ok": True,
            "output": f"markdown rendered ({len(args.get('markdown',''))} chars)"}


def create_diagram(args, ctx):
    kind = args.get("kind", args.get("type", "mermaid"))
    spec = args.get("spec", args.get("definition", ""))
    return {"ok": True,
            "output": f"diagram ({kind}):\n{spec[:2000]}"}


def generate_docs(args, ctx):
    return {"ok": True, "output": f"docs generated for {args.get('target','')}"}


def create_readme(args, ctx):
    path = args.get("path", os.path.join(ctx.workspace or ".",
                                         "README.md"))
    content = args.get("content", "# Project\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"ok": True, "output": f"wrote {path}"}


def generate_openapi(args, ctx):
    return {"ok": True, "output": "openapi spec generated (stub)"}


def create_changelog(args, ctx):
    return {"ok": True,
            "output": f"changelog entry: {args.get('entry','')}"}


# ================= 13. system admin =================
def _sys(cmd, ctx, timeout=60):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return {"ok": True, "output": f"exit={r.returncode}\n"
                + (r.stdout or "")[-4000:] + (r.stderr or "")[-1500:]}
    except Exception as e:
        return {"ok": False, "output": f"failed: {e}"}


def ps(args, ctx):
    return _sys("tasklist" if os.name == "nt" else "ps aux", ctx)


def df(args, ctx):
    return _sys("wmic logicaldisk get size,freespace,caption"
                if os.name == "nt" else "df -h", ctx)


def netstat(args, ctx):
    return _sys("netstat -ano", ctx)


def ping(args, ctx):
    host = args.get("host", "127.0.0.1")
    return _sys(f"ping -n 4 {host}" if os.name == "nt"
                else f"ping -c 4 {host}", ctx)


_APP_ALIASES = {
    "gtkwave": ["gtkwave"],
    "blender": ["blender"],
    "explorer": ["explorer.exe"],
    "files": ["explorer.exe"],
    "notepad": ["notepad.exe"],
    "vscode": ["code.cmd", "code"],
    "code": ["code.cmd", "code"],
    "chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "calc": ["calc.exe"],
    "paint": ["mspaint.exe"],
    "taskmgr": ["taskmgr.exe"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe"],
}


def _which_app(name: str, extra=()):
    import shutil
    for cand in list(extra) + [name]:
        p = shutil.which(cand)
        if p:
            return p
    return None


def open_app(args, ctx):
    """Launch an application, file, folder, or URL (detached)."""
    import shutil
    import subprocess
    name = str(args.get("name") or args.get("app") or "").strip()
    if not name:
        return {"ok": False, "output": "name required"}
    extra = args.get("args") or []
    if isinstance(extra, str):
        extra = [extra]
    extra = [str(a) for a in extra]
    cwd = args.get("cwd") or None

    # URLs and existing paths: let the shell association decide
    if name.lower().startswith(("http://", "https://", "mailto:")) \
            or os.path.exists(name):
        try:
            if cwd:
                os.startfile(name)
            else:
                os.startfile(name)
            return {"ok": True, "output": f"opened {name}"}
        except Exception as e:
            return {"ok": False, "output": f"open failed: {e}"}

    exe = _which_app(name, _APP_ALIASES.get(name.lower(), ()))
    if not exe and extra:
        exe = shutil.which(name) or name
    if exe:
        try:
            p = subprocess.Popen(
                [exe] + extra, cwd=cwd,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            return {"ok": True,
                    "output": f"launched {os.path.basename(exe)} "
                              f"(pid {p.pid})" +
                              (f" {' '.join(extra)}" if extra else "")}
        except Exception as e:
            return {"ok": False, "output": f"launch failed: {e}"}
    try:
        os.startfile(name)
        return {"ok": True, "output": f"opened {name}"}
    except Exception as e:
        return {"ok": False, "output": f"open failed: {e}"}


def clipboard_read(args, ctx):
    try:
        import ctypes
        CF_TEXT = 1
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard(0)
        h = user32.GetClipboardData(CF_TEXT)
        if not h:
            user32.CloseClipboard()
            return {"ok": True, "output": "(clipboard empty)"}
        data = ctypes.c_char_p(kernel32.GlobalLock(h)).value
        kernel32.GlobalUnlock(h)
        user32.CloseClipboard()
        return {"ok": True, "output": data.decode("utf-8", "replace")[:4000]}
    except Exception as e:
        return {"ok": False, "output": f"clipboard read failed: {e}"}


def system_status(args, ctx):
    import ctypes
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong)]
    ms = MS()
    ms.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    return {"ok": True, "output":
            f"ram_load={ms.dwMemoryLoad}% "
            f"free={ms.ullAvailPhys/1e9:.1f}GB "
            f"total={ms.ullTotalPhys/1e9:.1f}GB"}