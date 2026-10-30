"""Regression tests for the --json-repl stdin channel.

The desktop drives the agent over stdin/stdout. A blocking read on that
pipe stalls the rest of the process on Windows (a tool importing a module
never finishes), which used to freeze chip builds mid-turn. These tests
drive the real REPL with the same shape of pipe the app uses.
"""
import json
import os
import subprocess
import sys
import threading
import time

PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))
ENV = dict(os.environ)
ENV.setdefault("COAL_NO_35B", "1")

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    mark = "[ok]" if cond else "[FAIL]"
    print(f"  {mark} {name}{(' -> ' + detail) if detail else ''}")


class Repl:
    def __init__(self):
        self.t0 = time.time()
        self.events = []
        self.mode = None
        self.confirm = None
        self.tool_output = None
        self.done = None
        self.lock = threading.Lock()
        self.p = subprocess.Popen(
            [PY, "-u", "coal.py", "--json-repl"],
            cwd=HERE, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1, env=ENV)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.p.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            with self.lock:
                self.events.append(o)
                t = o.get("t")
                if t == "stdin-mode":
                    self.mode = o.get("mode")
                elif t == "confirm":
                    self.confirm = o
                elif t == "tool":
                    self.tool_output = o.get("output") or ""
                elif t == "done":
                    self.done = o

    def send(self, obj):
        with self.lock:
            self.p.stdin.write(json.dumps(obj) + "\n")
            self.p.stdin.flush()

    def wait_for(self, pred, timeout):
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                if pred():
                    return True
            time.sleep(0.1)
        return False

    def kill(self):
        try:
            self.p.kill()
        except Exception:
            pass


print("== 1. reader never blocks on the pipe ==")
r = Repl()
check("agent started", r.wait_for(lambda: r.mode is not None, 30),
      r.mode or "no stdin-mode event")
check("stdin is polled, not read blocking",
      r.mode in ("nonblocking", "peek"), f"mode={r.mode}")

print("== 2. approval gate still works ==")
r.send({"tool": "run_command", "args": {"command": "echo Coal-APPROVED"}})
check("confirm requested", r.wait_for(lambda: r.confirm is not None, 30))
r.send({"confirm": True})
check("approved command ran",
      r.wait_for(lambda: r.tool_output is not None, 30)
      and "Coal-APPROVED" in (r.tool_output or ""),
      repr((r.tool_output or "")[:60]))

print("== 3. denial stops the command ==")
r.confirm, r.tool_output, r.done = None, None, None
r.send({"tool": "run_command", "args": {"command": "echo Coal-DENIED"}})
check("confirm requested again", r.wait_for(lambda: r.confirm is not None, 30))
r.send({"confirm": False})
r.wait_for(lambda: r.done is not None, 30)
check("denied command did not run",
      "Coal-DENIED" not in (r.tool_output or ""),
      repr((r.tool_output or "")[:60]))

print("== 4. an importing tool completes while stdin is idle ==")
r.confirm, r.tool_output, r.done = None, None, None
started = time.time()
r.send({"tool": "chip_build",
        "args": {"spec": "4-bit gray to binary converter",
                 "name": "stdin_regression_chip"}})
finished = r.wait_for(lambda: r.done is not None, 120)
elapsed = time.time() - started
check("chip_build finished (no stall)", finished, f"{elapsed:.1f}s")
check("chip passed the gate", "PASS" in (r.tool_output or ""),
      (r.tool_output or "").splitlines()[0] if r.tool_output else "no output")
r.kill()

print("=" * 40)
ok = sum(1 for x in results if x)
print(f"{ok} passed, {len(results) - ok} failed")
sys.exit(0 if ok == len(results) else 1)
