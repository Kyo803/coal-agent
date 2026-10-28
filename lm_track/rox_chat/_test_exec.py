import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from rox import Rox

# auto-confirm tier-1 so the loop runs headless
r = Rox(session_name="toolexec", auto_start=False)
r.tctx.ask_callback = lambda p: "y"  # auto-approve for test

q = "create a file called notes.txt in my workspace that says: remember to test the API"
print("Q:", q)
ans, meta = r.respond(q, on_token=lambda t: None)
print(f"A [{meta['kind']}, {len(meta['tools'])} tools]: {ans[:200]}")
for t in meta["tools"]:
    print("   tool:", t[0], "->", t[2][:120])

# verify the file exists in the workspace
import os
p = os.path.expanduser("~/.rox/work/notes.txt")
print("file exists:", os.path.exists(p))
if os.path.exists(p):
    print("content:", open(p, encoding="utf-8").read()[:80])

r.close()