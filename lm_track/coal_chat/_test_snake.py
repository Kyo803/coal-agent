import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from coal import Coal

r = Coal(session_name="snake", auto_start=False, show_thinking=True)
r.tctx.ask_callback = lambda q: "y"  # auto-approve the file write

q = "make me a html + css + js script where I can play the classical snake game"
print("Q:", q)
ans, meta = r.respond(q, on_token=lambda t: None)
print("\nA:", ans)
for t in meta["tools"]:
    print("  tool:", t[0], "->", str(t[2])[:60])

# verify a file exists (workspace)
ws = os.path.expanduser("~/.coal/work")
files = sorted(os.listdir(ws))
print("\nworkspace files:", files[-5:])
for f in files:
    if f.endswith((".html", ".js", ".py", ".css", ".txt")):
        p = os.path.join(ws, f)
        sz = os.path.getsize(p)
        if sz > 500:
            print(f"  {f}: {sz} bytes | head: {repr(open(p,encoding='utf-8',errors='replace').read(60))}")
r.close()