import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from rox import Rox

r = Rox(session_name="rebrand2", auto_start=False)
r.tctx.ask_callback = lambda q: "y"  # auto-approve for headless test

q = "make a file called guard2.py on my desktop that blocks SQL injection"
print("Q:", q)
ans, meta = r.respond(q, on_token=lambda t: None)
print(f"A [{meta['kind']}, {len(meta['tools'])} tools]: {ans[:150]}")

p = os.path.join(os.path.expanduser("~"), "Desktop", "guard2.py")
print("file exists:", os.path.exists(p))
if os.path.exists(p):
    body = open(p, encoding="utf-8", errors="replace").read()
    print("size:", len(body), "chars")
    print("starts with:", repr(body[:60]))
    print("is real code (not tool-call wrapper):",
          "write_file(" not in body and body.strip().startswith(("import", "def", "from", "#", "class")))
r.close()