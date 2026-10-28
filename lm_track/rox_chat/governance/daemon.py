"""The always-on daemon: idle/night autonomous work.

Runs learning cycles when the user is idle (more at night), and optional
self-improvement. Uses the small model; never competes for the 35B unless
it is parked. Every action is telemetry-recorded.
"""
from __future__ import annotations

import os
import time

from rox_config import cfg

from . import resource, scheduler, telemetry

HEARTBEAT = os.path.join(cfg.memory_root, "heartbeat")
_LOG = os.path.join(os.path.dirname(HEARTBEAT), "governance", "daemon.log")
_LAST = os.path.join(os.path.dirname(HEARTBEAT), "governance", "last_run")


def _due(interval: float) -> bool:
    try:
        last = float(open(_LAST, encoding="utf-8").read().strip())
    except Exception:
        last = 0.0
    return (time.time() - last) >= interval


def _mark() -> None:
    try:
        os.makedirs(os.path.dirname(_LAST), exist_ok=True)
        with open(_LAST, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except Exception:
        pass


def _log(line: str) -> None:
    try:
        os.makedirs(os.path.dirname(_LOG), exist_ok=True)
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + line + "\n")
    except Exception:
        pass


def touch_heartbeat() -> None:
    try:
        os.makedirs(os.path.dirname(HEARTBEAT), exist_ok=True)
        with open(HEARTBEAT, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except Exception:
        pass


def _idle() -> tuple:
    try:
        age = time.time() - os.path.getmtime(HEARTBEAT)
    except Exception:
        age = 1e9
    return age, age >= float(scheduler.gc().get("idle_seconds", 120))


def run_task(t: dict) -> dict:
    name = t.get("task")
    from autonomy import activities
    return activities.run(name)


def tick(force_idle: bool = False) -> dict:
    age, idle = _idle()
    interval = float(scheduler.gc().get("interval_s", 900))
    if not force_idle and not _due(interval):
        telemetry.record("tick", idle=idle, age=int(age),
                         phase=scheduler.phase(), n=0, due=False)
        return {"idle": idle, "age": int(age), "phase": scheduler.phase(),
                "results": [], "due": False}
    tasks = scheduler.plan(idle_now=(idle or force_idle))
    if tasks:
        _mark()
    results = []
    for t in tasks:
        if not resource.can_run_heavy():
            results.append({"task": t.get("task"), "skipped": "low ram"})
            telemetry.record("skip", task=t.get("task"), reason="low ram")
            continue
        try:
            r = run_task(t)
            ok = bool(r.get("ok", True))
            results.append({"task": t.get("task"), "ok": ok})
            telemetry.record("task", task=t.get("task"), ok=ok)
        except Exception as e:
            results.append({"task": t.get("task"), "error": str(e)})
            telemetry.record("task_error", task=t.get("task"), error=str(e))
    telemetry.record("tick", idle=idle, age=int(age), phase=scheduler.phase(),
                     n=len(results))
    _log(f"tick phase={scheduler.phase()} idle={idle} "
         f"tasks={[t.get('task') for t in tasks]} results={results}")
    return {"idle": idle, "age": int(age), "phase": scheduler.phase(),
            "results": results}


_PID = os.path.join(os.path.dirname(HEARTBEAT), "governance", "daemon.pid")
_STOP = os.path.join(os.path.dirname(HEARTBEAT), "governance", "stop")


def _stop_requested() -> bool:
    return os.path.exists(_STOP)


def _housekeep() -> None:
    """24/7 hygiene: cap logs/telemetry, free memory."""
    import gc
    for fn in ("telemetry.jsonl", "daemon.log", "speed_cache.json",
               "router.json"):
        p = os.path.join(os.path.dirname(_LOG), fn)
        if os.path.exists(p):
            try:
                lines = open(p, encoding="utf-8",
                             errors="ignore").readlines()
                if len(lines) > 2000:
                    with open(p, "w", encoding="utf-8") as f:
                        f.writelines(lines[-2000:])
            except Exception:
                pass
    try:
        gc.collect()
    except Exception:
        pass


def stop():
    try:
        os.makedirs(os.path.dirname(_STOP), exist_ok=True)
        with open(_STOP, "w", encoding="utf-8") as f:
            f.write("1")
    except Exception:
        pass


def revoke():
    try:
        if os.path.exists(_STOP):
            os.remove(_STOP)
    except Exception:
        pass


def _already_running() -> bool:
    try:
        pid = int(open(_PID, encoding="utf-8").read().strip())
        os.kill(pid, 0)
        return pid != os.getpid()
    except Exception:
        return False


def daemon(once: bool = False, max_cycles: int = 0, poll=None) -> dict:
    if _already_running():
        _log("daemon already running; exiting")
        return {"ok": False, "reason": "daemon already running"}
    try:
        os.makedirs(os.path.dirname(_PID), exist_ok=True)
        with open(_PID, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    poll = poll if poll is not None else float(scheduler.gc().get("poll_s", 30))
    cycles = 0
    backoff = 1
    _log(f"daemon started pid={os.getpid()} poll={poll}")
    try:
        while True:
            if _stop_requested():
                _log("daemon stop requested")
                break
            try:
                tick()
            except Exception as e:
                _log(f"tick error: {e}")
                try:
                    telemetry.record("tick_error", error=str(e)[:200])
                except Exception:
                    pass
                time.sleep(backoff)
                backoff = min(backoff * 2, 600)
                continue
            backoff = 1
            cycles += 1
            if cycles % 60 == 0:
                _housekeep()
            if once or (max_cycles and cycles >= max_cycles):
                break
            time.sleep(poll)
    finally:
        try:
            os.remove(_PID)
        except Exception:
            pass
    return telemetry.summary()


def supervise(worker_args=("--daemon",)) -> dict:
    """Airtight 24/7 supervisor: relaunches the daemon worker forever."""
    import subprocess
    import sys as _sys
    py = _sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    py = pyw if os.path.exists(pyw) else py
    entry = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "rox.py")
    _log(f"supervisor started pid={os.getpid()} worker={entry}")
    while not _stop_requested():
        _log("supervisor launching worker")
        try:
            p = subprocess.Popen([py, entry] + list(worker_args),
                                 cwd=os.path.dirname(entry),
                                 creationflags=0x08000000)
            rc = p.wait()
            _log(f"worker exited rc={rc}; restart in 5s")
        except Exception as e:
            _log(f"supervisor worker launch failed: {e}")
            rc = -1
            time.sleep(10)
        if _stop_requested():
            break
        time.sleep(5)
    _log("supervisor ending")
    return {"supervisor": True, "pid": os.getpid()}
