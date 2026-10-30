import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from coal import Coal

r = Coal(session_name="projtest", auto_start=False)
r._confirm_prompt = lambda q: "you decide"

q = "create a project for my robot arm control system"
ans, meta = r.respond(q, on_token=lambda t: None)
print("Q:", q)
print("A:", ans.split("\n")[0])
print("project open:", r.project.name if r.project else None)

# write a file through Coal's own executor (so the journal hook applies)
if r.project:
    src = r.project.source
    os.makedirs(os.path.join(src, "src"), exist_ok=True)
    from tools.exec import ToolExecutor
    r.tctx.ask_callback = lambda q: "y"
    r.tctx.workspace = src
    r.tctx.project = r.project
    ex = ToolExecutor(r.tctx, r.perms)
    res = ex.run("write_file", {"path": os.path.join(src, "src", "main.py"),
                                "content": "import helper\n\ndef run():\n    return helper.add(1,2)\n"})
    print("write_file ok:", res.get("ok"))
    from project.journal import Journal
    j = Journal(r.project)
    print("journal count:", j.count())
    print(j.summary())
    from project.audit import Auditor
    rep = Auditor(r.project).audit()
    print("audit:", rep["counts"])

r.close()