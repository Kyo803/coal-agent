import sys, io, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from coal import Coal

r = Coal(session_name="repair3", auto_start=True)
r.tctx.ask_callback = lambda q: "y"
r._open_project("task-manager")
proj = r.project.source

req = ("rewrite the file called storage.py so it correctly handles Task "
       "objects: import Task from models; load(path) returns a list of "
       "Task objects (use Task.from_dict on each dict; return [] if the "
       "file is missing); save(path, tasks) serializes the list of Task "
       "objects to JSON using each task's to_dict().")
ans, meta = r.respond(req, on_token=lambda t: None)
print("A:", ans[:120])
r.project.scan()
r.close()

print("\n=== FULL PROJECT VERIFICATION ===")
ok = True
for mod in ["models", "storage", "service", "cli", "main"]:
    x = subprocess.run([sys.executable, "-c", f"import {mod}"], cwd=proj,
                       capture_output=True, text=True, timeout=60)
    st = "OK" if x.returncode == 0 else "FAIL"
    if st == "FAIL":
        ok = False
    print(f"  import {mod}: {st} {x.stderr.strip()[:90]}")

code = """
import os, tempfile
from service import TaskService
db = os.path.join(tempfile.mkdtemp(), 't.json')
s = TaskService(db)
a = s.add('write report', priority=1); s.add('buy milk')
s.complete(a.id)
print('list:', [(t.title, t.done) for t in s.list_all()])
print('search milk:', [t.title for t in s.search('milk')])
print('stats:', s.stats())
print('delete:', s.delete(a.id), '| left:', len(s.list_all()))
# reload from disk to prove persistence
s2 = TaskService(db)
print('persisted after reload:', [(t.title, t.done) for t in s2.list_all()])
"""
x = subprocess.run([sys.executable, "-c", code], cwd=proj,
                   capture_output=True, text=True, timeout=60)
print("\nfunctional:", x.stdout.strip() or ("ERR " + x.stderr.strip()[:300]))

print("\nCLI:")
for args in [["add", "test task"], ["list"], ["stats"]]:
    x = subprocess.run([sys.executable, "main.py"] + args, cwd=proj,
                       capture_output=True, text=True, timeout=60)
    print(f"  main.py {' '.join(args)} -> {(x.stdout or x.stderr).strip()[:140]}")