import sys, io, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from rox import Rox

r = Rox(session_name="repair4", auto_start=True)
r.tctx.ask_callback = lambda q: "y"
r._open_project("task-manager")
proj = r.project.source

req = ("rewrite the file called cli.py so it is correct: it must import "
       "TaskService from service and create it with a database path, "
       "e.g. TaskService('tasks.json') (use os.path.join with the script "
       "directory or a simple 'tasks.json'). Provide argparse subcommands "
       "add <title>, list, done <id>, delete <id>, search <query>, stats "
       "and a main() that runs them and prints results. The service "
       "methods are add(title, priority=2), list_all(), complete(id), "
       "delete(id), search(query), stats().")
ans, meta = r.respond(req, on_token=lambda t: None)
print("A:", ans[:120])
r.project.scan()
r.close()

print("\n=== FINAL CLI VERIFICATION ===")
for args in [["add", "write report"], ["add", "buy milk"],
             ["list"], ["stats"], ["search", "milk"]]:
    x = subprocess.run([sys.executable, "main.py"] + args, cwd=proj,
                       capture_output=True, text=True, timeout=60)
    out = (x.stdout or x.stderr).strip()
    print(f"  main.py {' '.join(args):22s} -> {out[:150]}")