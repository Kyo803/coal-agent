"""Tests for governance (scheduler, telemetry, resource, health, tick)."""
import time

PASS = FAIL = 0


def ok(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")


def main():
    from coal_config import cfg
    from governance import daemon, health, resource, scheduler, telemetry

    print("== 1. scheduler phase ==")
    night = time.struct_time((2026, 1, 1, 3, 0, 0, 0, 1, 0))
    day = time.struct_time((2026, 1, 1, 13, 0, 0, 0, 1, 0))
    ok("hour 3 -> night", scheduler.phase(night) == "night")
    ok("hour 13 -> day", scheduler.phase(day) == "day")

    print("== 2. scheduler plan ==")
    cfg["governance"]["enabled"] = False
    ok("disabled -> no tasks", scheduler.plan(True, day) == [])
    cfg["governance"]["enabled"] = True
    cfg["governance"]["run_learning"] = True
    cfg["governance"]["run_improve"] = False
    cfg["governance"]["night_cycles"] = 3
    nt = scheduler.plan(True, night)
    dt = scheduler.plan(True, day)
    ok("night -> 3 study", sum(1 for t in nt if t["task"] == "study") == 3)
    ok("day -> 1 study", sum(1 for t in dt if t["task"] == "study") == 1)
    ok("observe scheduled", any(t["task"] == "observe" for t in dt))
    ok("archive scheduled", any(t["task"] == "archive" for t in dt))
    ok("idle=False -> none", scheduler.plan(False, day) == [])

    print("== 3. telemetry ==")
    telemetry.record("test_event", x=1)
    s = telemetry.summary()
    ok("summary has events", "test_event" in s["events"])
    ok("satisfaction in [0,1]", 0.0 <= telemetry.satisfaction() <= 1.0)
    ok("generation metrics dict",
       isinstance(telemetry.generation_metrics(), dict))

    print("== 4. resource ==")
    r = resource.summary()
    ok("resource summary keys",
       {"host_free_ram_gb", "can_run_heavy"} <= set(r))

    print("== 5. health ==")
    h = health.snapshot()
    ok("health snapshot keys",
       {"server_35b", "ollama", "sandbox"} <= set(h))

    print("== 6. daemon tick (off = no tasks) ==")
    cfg["governance"]["enabled"] = False
    rep = daemon.tick(force_idle=True)
    ok("tick returns dict", isinstance(rep, dict) and "phase" in rep)
    ok("no tasks ran when disabled", rep["results"] == [])

    # restore defaults
    cfg["governance"]["enabled"] = False
    cfg["governance"]["run_learning"] = True
    cfg["governance"]["run_observe"] = True
    cfg["governance"]["run_archive"] = True

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
