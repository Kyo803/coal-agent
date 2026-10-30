"""Dev helper: drive coal.py --json-repl with one prompt."""
import json
import os
import subprocess
import sys
import threading
import time

prompt = sys.argv[1]
wait = float(sys.argv[2]) if len(sys.argv) > 2 else 240.0
auto = os.environ.get("AUTO_CONFIRM", "1") == "1"

t0 = time.time()
p = subprocess.Popen(
    [sys.executable, "-u", "coal.py", "--json-repl"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, text=True, bufsize=1)

done = {"v": False}

def pump():
    for line in p.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        t = o.get("t")
        if t == "token":
            continue
        if t == "tool":
            out = str(o.get("output") or "")
            print(f"{time.time()-t0:6.1f} TOOL {o.get('name')} -> "
                  f"{out[:260]!r}", flush=True)
        elif t == "confirm":
            print(f"{time.time()-t0:6.1f} CONFIRM {str(o.get('prompt'))[:100]!r}",
                  flush=True)
            if auto:
                p.stdin.write(json.dumps({"confirm": True}) + "\n")
                p.stdin.flush()
        elif t in ("answer", "done", "error", "stdin-mode"):
            print(f"{time.time()-t0:6.1f} {t.upper()} "
                  f"{json.dumps(o, default=str)[:700]}", flush=True)
            if t == "done":
                done["v"] = True
        elif t == "thinking":
            continue

threading.Thread(target=pump, daemon=True).start()
time.sleep(3)
p.stdin.write(json.dumps({"prompt": prompt}) + "\n")
p.stdin.flush()
print(f"{time.time()-t0:6.1f} SENT", flush=True)

end = time.time() + wait
while time.time() < end and not done["v"]:
    time.sleep(0.3)
print(f"{time.time()-t0:6.1f} END done={done['v']}", flush=True)
p.kill()
