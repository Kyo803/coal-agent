"""Tests for the new ROX N build capabilities (P1):
language packs, write-path injection, toolchain setup, autonomous
builder wiring, and safe self-modification.
"""
import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


print("== 1. language packs ==")
import langpacks as LP

installed = LP.install_curated()
check("install_curated returns packs", isinstance(installed, dict)
      and len(installed) >= 5, f"{list(installed)}")
packs = LP.list_packs()
for t in ("typescript", "tailwind", "react", "vite", "verilog"):
    check(f"pack present: {t}", t in packs)
root = LP.root()
for t in ("typescript", "react", "tailwind", "verilog", "vite"):
    p = os.path.join(root, t, "cheatsheet.md")
    check(f"cheatsheet on disk: {t}",
          os.path.exists(p) and os.path.getsize(p) > 100)

print("== 2. write-path langpack injection ==")
from rox import Rox

r = Rox(session_name="_t_build", auto_start=False)
check(".tsx -> react+tailwind+ts",
      r._langpack_context("src/App.tsx").find("useState") >= 0
      and "@tailwind" in r._langpack_context("src/App.tsx").lower()
      or "tailwind" in r._langpack_context("src/App.tsx").lower())
check(".css -> tailwind", "@tailwind" in r._langpack_context("a.css"))
check(".v -> verilog", "always" in r._langpack_context("cpu.v"))
check(".py -> empty", r._langpack_context("x.py") == "")
check(".ts -> typescript", len(r._langpack_context("x.ts")) > 200)

print("== 3. tool registry + intents ==")
from tools import specs as S
names = {s["name"] for s in S.SPECS}
for n in ("build_project", "setup_toolchain", "edit_self", "backup_self",
          "restore_self", "list_backups", "restart_self"):
    check(f"registered: {n}", n in names)
check("build_project is native", "build_project" in S.NATIVE_TOOLS)

from tools.intent import detect_intent
cases = {
    "build a project": "build_project",
    "build me a complete portfolio website with react and tailwind":
        "build_project",
    "create a full app called notes": "build_project",
    "scaffold a project": "build_project",
    "create a project for my todo app": "project_new",
    "make a snake game": "write_file",
}
for text, want in cases.items():
    got = detect_intent(text)
    check(f"intent {text[:34]!r} -> {want}",
          got is not None and got.tool == want,
          f"got {getattr(got, 'tool', None)}")

print("== 4. toolchain spec ==")
from tools.handlers_build import setup_toolchain, STACKS

check("web stack defined", "web" in STACKS and STACKS["web"]["dev"])
check("hdl uses winget", STACKS["hdl"].get("winget") == ["Icarus.Verilog"])
bad = setup_toolchain({"stack": "nope"}, r.tctx)
check("unknown stack rejected", bad["ok"] is False
      and "unknown stack" in bad["output"])

print("== 5. safe self-modification ==")
from tools.handlers_self import (backup_self, edit_self, list_backups,
                                 restore_self, _resolve)
tmpname = "_selftest_tmp.py"
tmppath = os.path.join(LP.root(), "..", "..")  # unused
real_tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), tmpname)
# valid edit
res = edit_self({"path": tmpname, "content": "x = 1\n"}, r.tctx)
check("edit_self writes valid file", res["ok"] and os.path.exists(real_tmp))
# invalid syntax rejected
res2 = edit_self({"path": tmpname, "content": "def broken(:\n"}, r.tctx)
check("edit_self rejects bad syntax", res2["ok"] is False
      and "SYNTAX ERROR" in res2["output"])
check("file unchanged after reject",
      open(real_tmp, encoding="utf-8").read() == "x = 1\n")
check("backups listed", "backups" in list_backups({}, r.tctx)["output"]
      or "no backups" in list_backups({}, r.tctx)["output"])
b = backup_self({"path": tmpname}, r.tctx)
check("backup_self works", b["ok"])
# cleanup
try:
    os.remove(real_tmp)
except Exception:
    pass
r.close()

print("=" * 40)
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)