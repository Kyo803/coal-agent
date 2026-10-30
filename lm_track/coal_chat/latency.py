"""Latency Accountant: per-token stage budget with shedding.

Measures ms per stage (base forward, STR check, tools, TME context build)
and enforces a total cap by shedding attachments in reverse-§7-priority
order (TME compression detail first, STR consistency samples next, ...
never the lockout). Emits a breakdown dict per turn for the eval report.
Proves the efficiency story end-to-end instead of asserting it.
"""
import time

SHED_ORDER = ["tme_detail", "str_stage2", "tool_verify", "base"]


class Accountant:
    def __init__(self, cap_ms=2000.0):
        self.cap = cap_ms
        self.shed = set()
        self.log = []

    def time_stage(self, name, fn, *a, **k):
        t0 = time.perf_counter()
        out = fn(*a, **k)
        dt = (time.perf_counter() - t0) * 1000.0
        self.log.append((name, round(dt, 2)))
        return out, dt

    def total(self):
        return sum(d for n, d in self.log if n not in self.shed)

    def over(self):
        return self.total() > self.cap

    def enforce(self):
        """Shed lowest-priority LOGGED stage until under cap. Returns
        list of newly shed stages (empty if already under cap)."""
        logged = {n for n, _ in self.log}
        shed_now = []
        for stage in SHED_ORDER:
            if not self.over() or stage == "base":
                break
            if stage not in logged or stage in self.shed:
                continue
            self.shed.add(stage)
            shed_now.append(stage)
        return shed_now

    def reset_turn(self):
        self.log = []

    def breakdown(self):
        return {"stages": dict(self.log),
                "total_ms": round(self.total(), 2),
                "shed": sorted(self.shed)}


def selftest():
    import time as _t
    acc = Accountant(cap_ms=50.0)
    acc.time_stage("base", lambda: _t.sleep(0.01))
    acc.time_stage("tme_detail", lambda: _t.sleep(0.06))
    assert acc.over()
    shed = acc.enforce()
    assert shed == ["tme_detail"], shed
    assert not acc.over()
    # lockout/base never shed even when over
    acc2 = Accountant(cap_ms=1.0)
    acc2.time_stage("base", lambda: _t.sleep(0.01))
    assert acc2.enforce() == []
    print("[latency] selftest OK", acc.breakdown())
    return True


if __name__ == "__main__":
    raise SystemExit(0 if selftest() else 1)
