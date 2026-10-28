import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from rox import Rox
from server_manager import ServerManager

r = Rox(session_name="imgtest", auto_start=True)
sm = ServerManager()
print("35B up before:", sm.health())

q = "make me an image of a cute robot arm"
print("Q:", q)
ans, meta = r.respond(q, on_token=lambda t: None)
print("A:", ans)
for n, a, res in meta["tools"]:
    print("  tool:", n, "->", str(res)[:120])

print("\n35B up after (reloaded):", sm.health())
# verify image exists
import glob
imgs = sorted(glob.glob(os.path.expanduser("~/.rox/work/images/*.png")))
print("generated images:", [os.path.basename(i) for i in imgs])
r.close()