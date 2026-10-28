import sys, io, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from rox import Rox
from server_manager import ServerManager

r = Rox(session_name="imgdbg", auto_start=True)
sm = ServerManager()
q = "generate a character for my game"
print("Q:", q)
ans, meta = r.respond(q, on_token=lambda t: None)
print("ANS:", repr(ans))
print("meta kind:", meta["kind"], "tools:", len(meta["tools"]))
for n, a, res in meta["tools"]:
    print("  tool:", n, "->", str(res)[:150])
print("35B up:", sm.health())
imgs = sorted(glob.glob(os.path.expanduser("~/.rox/work/images/*.png")))
print("images:", [os.path.basename(i) for i in imgs[-2:]])
r.close()