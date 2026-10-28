import sys, io, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
proj = r"C:\Users\WERU1\OneDrive\Desktop\ROX Projects\task-manager"

print("=== file list ===")
for f in sorted(os.listdir(proj)):
    print("  ", f)

print("\n=== import test ===")
for mod in ["models", "storage", "service", "cli", "main"]:
    r = subprocess.run([sys.executable, "-c", f"import {mod}; print('OK')"],
                       cwd=proj, capture_output=True, text=True, timeout=60)
    status = "OK" if r.returncode == 0 else "FAIL"
    print(f"  {mod}: {status} {r.stderr.strip()[:120]}")

print("\n=== functional smoke test ===")
code = """
import os, tempfile
from service import TaskService
db = os.path.join(tempfile.mkdtemp(), 'tasks.json')
svc = TaskService(db)
t = svc.add('write report', priority=1)
svc.add('buy milk')
svc.complete(t.id)
print('list:', [(x.title, x.done) for x in svc.list_all()])
print('search milk:', [x.title for x in svc.search('milk')])
print('stats:', svc.stats())
print('delete:', svc.delete(t.id))
print('after delete:', len(svc.list_all()))
"""
r = subprocess.run([sys.executable, "-c", code], cwd=proj,
                   capture_output=True, text=True, timeout=60)
print(r.stdout)
if r.stderr:
    print("ERR:", r.stderr[:400])

print("=== CLI test ===")
r = subprocess.run([sys.executable, "main.py", "add", "test task"],
                   cwd=proj, capture_output=True, text=True, timeout=60)
print("add:", (r.stdout or r.stderr).strip()[:150])
r = subprocess.run([sys.executable, "main.py", "list"],
                   cwd=proj, capture_output=True, text=True, timeout=60)
print("list:", (r.stdout or r.stderr).strip()[:200])
r = subprocess.run([sys.executable, "main.py", "stats"],
                   cwd=proj, capture_output=True, text=True, timeout=60)
print("stats:", (r.stdout or r.stderr).strip()[:150])