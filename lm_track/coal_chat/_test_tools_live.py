import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from coal import Coal

# headless test: auto-confirm so we can observe the tool loop
r = Coal(session_name="tooltest", auto_start=False)

q1 = "remember that I prefer dark mode on my laptop"
print("Q:", q1)
ans, meta = r.respond(q1, on_token=lambda t: None)
print(f"A [{meta['kind']}, {len(meta['tools'])} tools, {meta['ms']:.0f}ms]: {ans[:200]}")
for t in meta["tools"]:
    print("   tool:", t[0], "->", t[2][:80])

q2 = "search my memory: what do I prefer for dark mode?"
print("\nQ:", q2)
ans, meta = r.respond(q2, on_token=lambda t: None)
print(f"A [{meta['kind']}, {len(meta['tools'])} tools, {meta['ms']:.0f}ms]: {ans[:200]}")
for t in meta["tools"]:
    print("   tool:", t[0], "->", t[2][:80])

r.close()