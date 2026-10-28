"""Heavy multi-file coding test: drive ROX N to build a layered
task-manager project file-by-file, then verify imports + run it."""
import sys, io, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from rox import Rox

r = Rox(session_name="coding-test", auto_start=True)
r.tctx.ask_callback = lambda q: "y"   # auto-approve file writes
r._confirm_prompt = lambda q: "you decide"

# 1. create the project
r._open_project("task-manager")
print("PROJECT:", r.project.source)

SPECS = [
    ("models.py",
     "make a file called models.py containing a Python dataclass Task "
     "with fields id:int, title:str, done:bool=False, priority:int=2, "
     "created:str=''. Include to_dict() and a classmethod from_dict(d). "
     "Pure stdlib (dataclasses)."),
    ("storage.py",
     "make a file called storage.py with functions load(path) -> list "
     "(returns [] if the file is missing) and save(path, tasks:list) "
     "that writes JSON. Import json and os. Pure stdlib."),
    ("service.py",
     "make a file called service.py that imports Task from models and "
     "load/save from storage. Define class TaskService(path) with "
     "methods: add(title, priority=2)->Task, list_all()->list, "
     "complete(task_id)->bool, delete(task_id)->bool, search(query)->"
     "list, stats()->dict (total/done/pending). Persist after each "
     "mutation via storage.save."),
    ("cli.py",
     "make a file called cli.py that imports TaskService from service "
     "and uses argparse to provide subcommands: add <title>, list, "
     "done <id>, delete <id>, search <query>, stats. Include a main() "
     "that parses args and prints results."),
    ("main.py",
     "make a file called main.py that imports main from cli and calls "
     "it when run as __main__."),
]

for name, req in SPECS:
    print(f"\n=== writing {name} ===")
    ans, meta = r.respond(req, on_token=lambda t: None)
    print(" ", ans[:120])
    for n, a, res in meta["tools"]:
        print("   tool:", n, "->", str(res)[:90])

# 2. verify the files exist
print("\n=== project tree ===")
arch = r.project.architecture(refresh=True)
for f in arch["tree"]:
    print("  ", f)
for mo in arch["modules"]:
    print("  ", mo["path"], "->", [s["name"] for s in mo["symbols"]][:8])

# 3. audit
from project.audit import Auditor
rep = Auditor(r.project).audit()
print("\n=== audit ===", rep["counts"])

r.close()
print("\nDONE. project at:", r.project.source)