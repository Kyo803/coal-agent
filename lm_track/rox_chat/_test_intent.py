import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from tools.intent import detect_intent, needs_force
from tools.exec import lazy_schemas
from tools.permissions import Permissions

p = Permissions()
cases = [
    ("make a file called guard.py on my desktop that blocks SQL injection",
     "write_file", "high", "write_file"),
    ("remember that I like dark mode", "remember", "high", "remember"),
    ("what do I prefer on my laptop", "search_memory", "high",
     "search_memory"),
    ("what is 2 + 2", "chat", "low", None),
    ("hello there", "chat", "low", None),
    ("git status", "git_status", "medium", "git_status"),
    ("read the file notes.txt", "read_file", "medium", "read_file"),
]
ok = 0
for q, want_tool, want_conf, want_schema in cases:
    i = detect_intent(q)
    schemas = lazy_schemas(q, p)
    names = {x["function"]["name"] for x in schemas}
    t_ok = i.tool == want_tool
    c_ok = i.confidence == want_conf
    s_ok = (want_schema is None) or (want_schema in names)
    force = needs_force(i)
    if t_ok and c_ok and s_ok:
        ok += 1
        print(f"  [ok] {q[:40]:42s} -> {i.tool} [{i.confidence}] "
              f"force={force}")
    else:
        print(f"  [FAIL] {q[:40]:42s} -> {i.tool} [{i.confidence}] "
              f"(want {want_tool} [{want_conf}]) schema_in={s_ok}")
print(f"{ok}/{len(cases)} intent cases passed")