import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from rox import Rox

r = Rox(session_name="verify", auto_start=False)
q = "what is 12 * 9?"
ans, meta = r.respond(q, on_token=lambda t: None)
print(f"Q: {q}")
print(f"A [{meta['kind']}]: {ans[:120]}")
r.close()