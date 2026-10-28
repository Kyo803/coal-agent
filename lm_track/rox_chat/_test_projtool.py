import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from tools.exec import ToolExecutor, ExecContext
from tools.permissions import Permissions

# test project_new via executor (confirm gate)
ctx = ExecContext(workspace="~/.rox/work", ask_callback=lambda q: "y")
ctx.project = None
ex = ToolExecutor(ctx, Permissions())
r = ex.run("project_new", {"name": "tmp-test-proj"})
print("project_new:", r.get("ok"), "|", r.get("output", "").split("\n")[0])
name = r.get("output", "").split("'")[1] if "'" in r.get("output","") else ""
import shutil
from project import Project
p = Project.open("tmp-test-proj")
shutil.rmtree(p.source, ignore_errors=True)
shutil.rmtree(p.ledger, ignore_errors=True)
print("cleaned tmp-test-proj")
print("done")