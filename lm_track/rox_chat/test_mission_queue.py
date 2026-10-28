"""Tests for the mission queue."""
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
    from builder import mission_queue as Q
    from builder import missions as M

    print("== 1. queue seeding ==")
    s = Q.summary()
    tierA = {"alu8", "bshift", "counter4", "fifo8", "uart_tx", "pwm",
             "spi4", "seg7"}
    ok("tier-A present", tierA <= set(s["order"]))
    ok("all specs exist", all(M.load(n) is not None for n in s["order"]))

    print("== 2. reset / mark / next ==")
    Q.reset()
    ok("reset all pending", Q.summary()["n_pending"] == len(s["order"]))
    Q.mark("alu8", "done")
    ok("mark done", "alu8" in Q.summary()["done"])
    ok("next skips done", Q.next_mission() != "alu8")
    Q.mark("bshift", "failed")
    ok("mark failed", "bshift" in Q.summary()["failed"])

    print("== 3. restore ==")
    Q.reset()
    ok("restored pending", Q.summary()["n_pending"] == len(s["order"]))

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)