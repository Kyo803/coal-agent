import sys, io, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from rox import Rox

r = Rox(session_name="repair", auto_start=False)
r._open_project("task-manager")
r.tctx.ask_callback = lambda q: "y"
proj = r.project.source

# ROX N fixes the import via its own edit_file tool
bad = "from models import Task, to_dict, from_dict"
good = "from models import Task"
res = r.texec.run("edit_file", {"path": os.path.join(proj, "service.py"),
                                "old": bad, "new": good})
print("edit_file:", res.get("ok"), res.get("output", "")[:80])
r.project.scan()
r.close()

print("\n=== re-verify after repair ===")
for mod in ["models", "storage", "service", "cli", "main"]:
    x = subprocess.run([sys.executable, "-c", f"import {mod}"], cwd=proj,
                       capture_output=True, text=True, timeout=60)
    print(f"  import {mod}: {'OK' if x.returncode == 0 else 'FAIL'} "
          f"{x.stderr.strip()[:100]}")

code = """
import os, tempfile
from service import TaskService
db = os.path.join(tempfile.mkdtemp(), 'tasks.json')
svc = TaskService(db)
t = svc.add('write report', priority=1); svc.add('buy milk')
svc.complete(t.id)
print('list:', [(x.title, x.done) for x in svc.list_all()])
print('search:', [x.title for x in svc.search('milk')])
print('stats:', svc.stats())
print('delete:', svc.delete(t.id), '| remaining:', len(svc.list_all()))
"""
x = subprocess.run([sys.executable, "-c", code], cwd=proj,
                   capture_output=True, text=True, timeout=60)
print("\nfunctional:", x.stdout.strip() or x.stderr.strip()[:300])

print("\nCLI:")
for args in [["add", "test task"], ["list"], ["stats"]]:
    x = subprocess.run([sys.executable, "main.py"] + args, cwd=proj,
                       capture_output=True, text=True, timeout=60)
    print(f"  main.py {' '.join(args)}:",
          (x.stdout or x.stderr).strip()[:120])