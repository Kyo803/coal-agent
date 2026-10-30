"""Tests for the autonomy brain (offline; no network, no model)."""
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
    from autonomy import brain, activities, loop
    from autonomy import activities as act

    print("== 1. brain facade ==")
    st = brain.status()
    ok("status has mood/graph/focus",
       {"mood", "graph", "focus"} <= set(st))

    print("== 2. activity dispatch ==")
    ok("known activities present",
       {"study", "observe", "practice", "reflect", "improve",
        "archive"} <= set(act.ACTIVITIES))
    unknown = activities.run("nonsense")
    ok("unknown activity refused", unknown["ok"] is False)

    print("== 3. observe offline ==")
    obs = brain.observe(network=False)
    ok("observe ok offline", obs.get("ok") is True)

    print("== 4. reflect ==")
    ref = brain.reflect(measure=False)
    ok("reflect ok", ref.get("ok") is True)
    ok("reflect has satisfaction", "satisfaction" in ref)

    print("== 5. reflect has board ==")
    refl = act.reflect(measure=False)
    ok("reflect ok", refl.get("ok") is True)
    ok("reflect has satisfaction", "satisfaction" in refl)

    print("== 6. board bridge ==")
    from learning import board_bridge
    wrote = board_bridge.record_cycle("autonomy_test_topic", mastery=0.3,
                                      summary="test", sources=["http://x"])
    ok("board bridge returns bool", isinstance(wrote, bool))

    print("== 7. governance dispatch ==")
    from governance import daemon
    rep = daemon.run_task({"task": "reflect"})
    ok("daemon dispatches reflect", isinstance(rep, dict))

    print("== 8. loop ==")
    ok("loop has tick", callable(loop.tick))

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
