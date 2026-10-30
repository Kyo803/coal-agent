import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server_manager import ServerManager, free_ram_gb
from board.store import BoardStore
from board.archivist import Archivist
from memory import Embedder, VectorIndex

root = os.path.expanduser("~/.coal")
st = BoardStore(os.path.join(root, "board.db"))
em = Embedder()
ix = VectorIndex(os.path.join(root, "vectors"), dim=em.dim)
sm = ServerManager()

print(f"[live] free RAM before park: {free_ram_gb():.1f} GB")
print("[live] parking 35B ...")
sm.stop()
for _ in range(60):
    if free_ram_gb() >= 5.0:
        break
    time.sleep(2)
print(f"[live] free RAM after park: {free_ram_gb():.1f} GB")

a = Archivist(st, em, ix, server_manager=sm)
if not a.available():
    print("[live] ollama unavailable")
else:
    job = {"user_text": "I'm building an industrial robot arm with NEMA 23 "
                        "stepper motors and a 4A driver.",
           "thinking": "The user is describing a hardware project. They have "
                       "chosen NEMA 23 motors. I should remember the project "
                       "and the motor choice.",
           "output": "Nice project. NEMA 23 steppers pair well with a 4A "
                     "microstepping driver; want help picking one?"}
    t0 = time.time()
    data = a.extract(job)
    print(f"[live] extract took {time.time()-t0:.1f}s")
    print("[live] extracted JSON:")
    print(json.dumps(data, indent=1)[:1200])

print("[live] reloading 35B ...")
sm.ensure()
print("[live] done")
st.close()
