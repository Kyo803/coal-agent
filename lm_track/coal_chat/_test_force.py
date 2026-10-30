import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from coal import Coal

r = Coal(session_name="force", auto_start=False)
# auto-confirm write_file so the loop completes
r.tctx.ask_callback = lambda q: "y"

q = "make a file called guard.py on my desktop that blocks SQL injection"
print("Q:", q)
ans, meta = r.respond(q, on_token=lambda t: None)
print(f"A [{meta['kind']}, {len(meta['tools'])} tools]: {ans[:200]}")
for t in meta["tools"]:
    print("   tool:", t[0], "->", str(t[2])[:100])

# verify the file
desk = os.path.join(os.path.expanduser("~"), "Desktop", "guard.py")
print("desktop file exists:", os.path.exists(desk))
if os.path.exists(desk):
    sz = os.path.getsize(desk)
    print("size:", sz, "bytes")
    head = open(desk, encoding="utf-8", errors="replace").read(200)
    print("head:", repr(head[:120]))

r.close()