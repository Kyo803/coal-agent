import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from coal import Coal

r = Coal(session_name="liveproj", auto_start=False)
r._confirm_prompt = lambda q: "my-arm"  # user provides a name

q = "create a project for my industrial robot arm"
ans, meta = r.respond(q, on_token=lambda t: None)
print("Q:", q)
print("A:", ans)
print("project:", r.project.name if r.project else None)
print("source:", r.project.source if r.project else None)
r.close()