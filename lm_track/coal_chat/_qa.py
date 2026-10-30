import sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from coal import Coal

r = Coal(session_name="qa", auto_start=False)
r.tctx.ask_callback = lambda q: "y"

q = "can you check that snake project for me"
print("Q:", q)
ans, meta = r.respond(q, on_token=lambda t: None)
print("A:", ans[:300])
print("\nTOOL TRACE:")
for name, args, res in meta["tools"]:
    print(f"  tool={name} args={json.dumps(args)[:100]}")
    print(f"    res={str(res)[:200]}")
r.close()