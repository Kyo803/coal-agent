import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from coal import Coal

r = Coal(session_name="finalcheck", auto_start=False)

# memory recall
q1 = "what motors do I use on my robot arm?"
ans, meta = r.respond(q1, on_token=lambda t: None)
print(f"Q: {q1}\nA [{meta['kind']}]: {ans[:120]}")

# intent write to workspace (not desktop, to avoid clutter)
q2 = "make a file called hello.py that prints hello world"
ans, meta = r.respond(q2, on_token=lambda t: None)
print(f"\nQ: {q2}\nA [{meta['kind']}, {len(meta['tools'])} tools]: {ans[:120]}")
import os
p = os.path.expanduser("~/.coal/work/hello.py")
print("workspace hello.py exists:", os.path.exists(p),
      "| content:", open(p, encoding="utf-8").read(60) if os.path.exists(p) else "-")

# multi-language run_script via model? test executor directly instead
from tools.exec import ToolExecutor, ExecContext
from tools.permissions import Permissions
ex = ToolExecutor(ExecContext(workspace="~/.coal/work",
                              ask_callback=lambda q: "y"), Permissions())
rr = ex.run("run_script", {"language": "node", "code": "console.log(40+2)"})
print("\nrun_script node:", rr["output"].strip())

r.close()