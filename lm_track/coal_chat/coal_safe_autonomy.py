"""Safe unattended autonomy runner for Coal.

Hard rules (learned from two crashes on this machine):
  1. NEVER start the 19.7 GB 35B model server — it does not fit in 24 GB
     beside the user's own work. It is actively stopped if it appears.
  2. NEVER run when free physical RAM is below FLOOR_GB.
  3. Run everything at BELOW_NORMAL priority so the user's work always wins.
  4. One daemon at a time; restart on death with backoff; honour STOP file.
  5. Log + heartbeat so the run is visible and auditable.

    python coal_safe_autonomy.py            # run (foreground, Ctrl-C safe)
    python coal_safe_autonomy.py --status   # show state
    python coal_safe_autonomy.py --stop     # ask it to stop
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
Coal = os.path.join(HERE, "coal.py")
STATE = os.path.join(os.path.expanduser("~"), ".coal", "autonomy")
LOG = os.path.join(STATE, "safe-autonomy.log")
STOP = os.path.join(STATE, "STOP")
HEART = os.path.join(STATE, "heartbeat")
PIDF = os.path.join(STATE, "supervisor.pid")

FLOOR_GB = float(os.environ.get("COAL_FLOOR_GB", "5.0"))
POLL = float(os.environ.get("COAL_SUP_POLL", "30"))
MAX_HOURS = float(os.environ.get("COAL_MAX_HOURS", "84"))     # 3.5 days
STALL_MIN = float(os.environ.get("COAL_STALL_MIN", "25"))     # restart if stuck
BACKOFF = [10, 30, 60, 120, 300, 600]
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
GOV = os.path.join(os.path.expanduser("~"), ".coal", "governance")


def _progress_time():
    """Newest mtime of the daemon's progress files (0 if none)."""
    newest = 0.0
    for p in (os.path.join(GOV, "daemon.log"),
              os.path.join(GOV, "telemetry.jsonl"),
              os.path.join(GOV, "last_run")):
        try:
            newest = max(newest, os.path.getmtime(p))
        except Exception:
            pass
    return newest


def log(msg):
    line = time.strftime("%Y-%m-%dT%H:%M:%S ") + str(msg)
    try:
        os.makedirs(STATE, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        # keep the log bounded
        if os.path.getsize(LOG) > 2_000_000:
            with open(LOG, encoding="utf-8", errors="ignore") as f:
                tail = f.readlines()[-2000:]
            with open(LOG, "w", encoding="utf-8") as f:
                f.writelines(tail)
    except Exception:
        pass
    print(line, flush=True)


def free_ram_gb():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MS()
    st.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPhys / (1024 ** 3)


def _pids(name):
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Process {name} -ErrorAction SilentlyContinue | "
             f"Select-Object -ExpandProperty Id"],
            capture_output=True, text=True, timeout=30).stdout
        return [int(x) for x in out.split() if x.strip().isdigit()]
    except Exception:
        return []


def kill_35b():
    """The 35B must never run unattended on this machine."""
    n = 0
    for p in _pids("llama-server"):
        log(f"SAFETY: stopping 35B llama-server pid={p}")
        subprocess.run(["taskkill", "/F", "/PID", str(p)],
                       capture_output=True, timeout=30)
        n += 1
    return n


def set_below_normal(pid):
    try:
        h = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, int(pid))
        if h:
            ctypes.windll.kernel32.SetPriorityClass(
                h, BELOW_NORMAL_PRIORITY_CLASS)
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        pass


def heartbeat(**extra):
    try:
        with open(HEART, "w", encoding="utf-8") as f:
            json.dump({"t": time.time(), "free_gb": round(free_ram_gb(), 2),
                       **extra}, f)
    except Exception:
        pass


def _stop_requested():
    return os.path.exists(STOP)


def status():
    st = {"stop_file": os.path.exists(STOP), "free_gb": round(free_ram_gb(), 2),
          "floor_gb": FLOOR_GB, "llama_server_pids": _pids("llama-server"),
          "ollama_pids": _pids("ollama"),
          "supervisor_running": bool(_pids("python"))}
    for p in (PIDF, HEART, LOG):
        st[os.path.basename(p)] = (open(p, encoding="utf-8").read()[:300]
                                   if os.path.exists(p) else None)
    print(json.dumps(st, indent=1))
    return st


def main():
    if "--status" in sys.argv:
        return status()
    if "--stop" in sys.argv:
        open(STOP, "w", encoding="utf-8").write("1")
        log("stop requested by user")
        return {"ok": True}

    os.makedirs(STATE, exist_ok=True)
    open(PIDF, "w", encoding="utf-8").write(str(os.getpid()))
    log(f"=== safe autonomy supervisor start pid={os.getpid()} "
        f"floor={FLOOR_GB}GB max={MAX_HOURS}h ===")
    if os.path.exists(STOP):
        os.remove(STOP)

    t0 = time.time()
    backoff_i = 0
    try:
        while True:
            if _stop_requested():
                log("stop file found -> exiting")
                break
            if (time.time() - t0) > MAX_HOURS * 3600:
                log("max runtime reached -> exiting")
                break
            kill_35b()
            free = free_ram_gb()
            if free < FLOOR_GB:
                log(f"RAM low ({free:.1f} GB < {FLOOR_GB}) -> waiting")
                heartbeat(state="waiting_ram", free_gb=round(free, 2))
                time.sleep(POLL)
                continue

            # cap Ollama's share so the user's work stays responsive
            for p in _pids("ollama"):
                set_below_normal(p)

            log(f"starting daemon (free {free:.1f} GB)")
            env = dict(os.environ)
            env["COAL_FLOOR_GB"] = str(FLOOR_GB)
            env["CoalO_35B"] = "1"      # the 19.7 GB model must never start
            pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            exe = pyw if os.path.exists(pyw) else sys.executable
            p = subprocess.Popen([exe, Coal, "--daemon"], cwd=HERE, env=env,
                                 creationflags=0x08000000)
            set_below_normal(p.pid)
            heartbeat(state="running", daemon_pid=p.pid,
                      free_gb=round(free, 2))
            log(f"daemon pid={p.pid} (below-normal)")
            # supervise: poll RAM + watch for a stalled tick
            last_progress = _progress_time() or time.time()
            ticks = 0
            while p.poll() is None:
                ticks += 1
                if ticks % 10 == 0:      # keep the 35B down while running
                    kill_35b()
                if _stop_requested():
                    log("stop -> terminating daemon")
                    p.terminate()
                    break
                if (time.time() - t0) > MAX_HOURS * 3600:
                    p.terminate()
                    break
                free = free_ram_gb()
                if free < FLOOR_GB:
                    log(f"RAM low ({free:.1f} GB) -> pausing daemon")
                    try:
                        p.terminate()
                    except Exception:
                        pass
                    break
                prog = _progress_time()
                if prog > last_progress:
                    last_progress = prog
                elif (time.time() - last_progress) > STALL_MIN * 60:
                    log(f"no progress for {STALL_MIN:.0f} min -> "
                        f"restarting stalled daemon")
                    try:
                        p.terminate()
                        time.sleep(5)
                        if p.poll() is None:
                            p.kill()
                    except Exception:
                        pass
                    break
                heartbeat(state="running", daemon_pid=p.pid,
                          free_gb=round(free, 2))
                time.sleep(POLL)
            rc = p.poll()
            log(f"daemon exited rc={rc}")
            if _stop_requested():
                break
            wait = BACKOFF[min(backoff_i, len(BACKOFF) - 1)]
            backoff_i += 1
            log(f"restarting in {wait}s")
            time.sleep(wait)
    except KeyboardInterrupt:
        log("interrupted")
    finally:
        try:
            os.remove(PIDF)
        except Exception:
            pass
        log("=== supervisor stopped ===")
    return {"ok": True}


if __name__ == "__main__":
    main()
