import sys, io, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from coal import Coal

r = Coal(session_name="repair2", auto_start=True)
r.tctx.ask_callback = lambda q: "y"
r._open_project("task-manager")
proj = r.project.source

# Coal rewrites service.py with a spec that names the real interface
req = ("rewrite the file called service.py so it is correct: Task is a "
       "dataclass with fields id, title, done (bool), priority, created "
       "and methods to_dict() and from_dict(). TaskService(path) must "
       "load() tasks, add(title, priority=2) creating a Task with a new "
       "id (max existing id + 1) and created timestamp, list_all() "
       "returning the Task objects, complete(id) setting .done=True, "
       "delete(id), search(query) matching title, stats() returning "
       "total/done/pending using .done. Save after each mutation.")
ans, meta = r.respond(req, on_token=lambda t: None)
print("A:", ans[:140])
r.project.scan()
r.close()

print("\n=== verify full project ===")
for mod in ["models", "storage", "service", "cli", "main"]:
    x = subprocess.run([sys.executable, "-c", f"import {mod}"], cwd=proj,
                       capture_output=True, text=True, timeout=60)
    print(f"  import {mod}: {'OK' if x.returncode == 0 else 'FAIL ' + x.stderr.strip()[:90]}")

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
"""
x = subprocess.run([sys.executable, "-c", code], cwd=proj,
                   capture_output=True, text=True, timeout=60)
print("\nfunctional:", x.stdout.strip() or ("ERR " + x.stderr.strip()[:300]))

print("\nCLI:")
for args in [["add", "test task"], ["list"], ["stats"]]:
    x = subprocess.run([sys.executable, "main.py"] + args, cwd=proj,
                       capture_output=True, text=True, timeout=60)
    print(f"  main.py {' '.join(args)} -> {(x.stdout or x.stderr).strip()[:130]}")