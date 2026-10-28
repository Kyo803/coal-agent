import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
# simulate chat_loop's printing logic
from rox import Rox, chat_loop
import rox as R

r = Rox(session_name="chatprint", auto_start=True)

# 1. non-streamed path (image gen) - ans must print
streamed = [False]
def _tok(t):
    streamed[0] = True
q = "make me an image of a mountain"
ans, meta = r.respond(q, on_token=_tok)
print("streamed?", streamed[0], "| printed answer:", repr(ans[:50]))
print("meta:", meta["kind"], len(meta["tools"]))

# 2. streamed chat path
streamed = [False]
q2 = "what is 2+2?"
ans2, meta2 = r.respond(q2, on_token=_tok)
print("\nchat streamed?", streamed[0], "| answer:", repr(ans2[:40]))
r.close()