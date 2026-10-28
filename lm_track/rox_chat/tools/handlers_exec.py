"""Category 3 handlers: execution + runtime.
"""
from __future__ import annotations

import os
import subprocess
import sys


def _run(cmd, ctx, timeout=60):
    shell = os.name == "nt"
    try:
        r = subprocess.run(cmd, shell=shell, capture_output=True, text=True,
                           timeout=timeout, cwd=ctx.workspace or None,
                           encoding="utf-8", errors="replace")
        return {"ok": True, "output": f"exit={r.returncode}\n"
                + (r.stdout or "")[-4000:] + (r.stderr or "")[-2000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"timeout after {timeout}s"}
    except Exception as e:
        return {"ok": False, "output": f"exec failed: {e}"}


def run_command(args, ctx):
    from . import shell
    return shell.run_safe(args.get("command", args.get("cmd", "")),
                          workspace=getattr(ctx, "workspace", None),
                          ask_callback=getattr(ctx, "ask_callback", None),
                          timeout=int(args.get("timeout", 90)),
                          cwd=args.get("cwd"))


def bash(args, ctx):
    return run_command(args, ctx)


def run_script(args, ctx):
    lang = args.get("language", args.get("lang", "python"))
    code = args.get("code", "")
    if lang == "python":
        return _run([sys.executable, "-c", code], ctx)
    return _run(code, ctx)


def python_repl(args, ctx):
    return run_script({"language": "python", "code": args.get("code", "")}, ctx)


def background_process_start(args, ctx):
    cmd = args.get("command", "")
    log = args.get("log", "bg.log")
    try:
        path = os.path.join(ctx.workspace or ".", log)
        with open(path, "w", encoding="utf-8") as lf:
            subprocess.Popen(cmd, shell=True, stdout=lf, stderr=subprocess.STDOUT,
                             cwd=ctx.workspace or None,
                             creationflags=0x00000008 | 0x00000200)
        return {"ok": True, "output": f"started bg: {cmd} (log {path})"}
    except Exception as e:
        return {"ok": False, "output": f"start failed: {e}"}


def process_list(args, ctx):
    return _run("tasklist" if os.name == "nt" else "ps aux", ctx, timeout=20)


def process_kill(args, ctx):
    pid = args.get("pid", args.get("name", ""))
    if os.name == "nt":
        cmd = f"taskkill /F /PID {pid}" if str(pid).isdigit() \
            else f"taskkill /F /IM {pid}"
    else:
        cmd = f"kill -9 {pid}" if str(pid).isdigit() else f"pkill -f {pid}"
    return _run(cmd, ctx, timeout=20)


def tail_logs(args, ctx):
    import glob as g
    log = args.get("log", args.get("path", "*.log"))
    pattern = os.path.join(ctx.workspace or ".", log)
    files = g.glob(pattern)
    if not files:
        return {"ok": False, "output": f"no log files matching {pattern}"}
    path = files[-1]
    n = int(args.get("lines", 50))
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
        return {"ok": True, "output": f"{path}\n" + "\n".join(lines[-n:])}
    except Exception as e:
        return {"ok": False, "output": f"read failed: {e}"}


def env_get(args, ctx):
    return {"ok": True, "output": os.environ.get(args.get("key", ""), "")}


def env_set(args, ctx):
    os.environ[args.get("key", "")] = str(args.get("value", ""))
    return {"ok": True, "output": f"set {args.get('key')}"}


def set_working_directory(args, ctx):
    ctx.workspace = os.path.abspath(os.path.expanduser(args.get("path", ".")))
    return {"ok": True, "output": f"cwd -> {ctx.workspace}"}


def run_tests(args, ctx):
    return _run(args.get("command", args.get("cmd", "python -m pytest -q")),
                ctx, timeout=int(args.get("timeout", 300)))


def run_single_test(args, ctx):
    name = args.get("test", args.get("name", ""))
    return _run(f"python -m pytest {name} -q", ctx,
                timeout=int(args.get("timeout", 300)))


def run_linter(args, ctx):
    return _run(args.get("command", "python -m pyflakes ."), ctx, timeout=120)


def run_formatter(args, ctx):
    return _run(args.get("command", "python -m black --check ."), ctx, timeout=120)


def type_check(args, ctx):
    return _run(args.get("command", "python -m mypy ."), ctx, timeout=180)


def build(args, ctx):
    return _run(args.get("command", "python -m build"), ctx, timeout=300)


def install_package(args, ctx):
    pkg = args.get("package", args.get("name", ""))
    mgr = args.get("manager", "pip")
    return _run(f"{mgr} install {pkg}", ctx, timeout=300)


def run_benchmark(args, ctx):
    return _run(args.get("command", ""), ctx, timeout=300)


def profile_memory(args, ctx):
    import tracemalloc
    tracemalloc.start()
    code = args.get("code", "pass")
    try:
        exec(code, {"__builtins__": __builtins__})
    except Exception as e:
        return {"ok": False, "output": str(e)}
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"ok": True, "output":
            f"current={cur/1024:.0f}KB peak={peak/1024:.0f}KB"}

def node_repl(args, ctx):
    return run_script({"language": "node", "code": args.get("code", "")}, ctx)


def code_interpreter(args, ctx):
    return run_script({"language": "python", "code": args.get("code", "")}, ctx)


def jupyter_execute(args, ctx):
    return run_script({"language": "python", "code": args.get("code", "")}, ctx)

