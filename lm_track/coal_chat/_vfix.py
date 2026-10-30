import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from coal import Coal
r = Coal(session_name="v2", auto_start=False)
ans, meta = r.respond("read my snake.html and tell me what it does",
                      on_token=lambda t: None)
print("A:", ans[:180])
print(f"[{meta['kind']}, {len(meta['tools'])} tools]")
for n, a, res in meta["tools"]:
    print("  tool=", n, "res head=", str(res)[:60])
r.close()