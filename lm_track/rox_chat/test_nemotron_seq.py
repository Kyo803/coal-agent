"""Nemotron sequential-design battery: where the model is weakest.

Same protocol as test_nemotron_novel.py, but every design is clocked/stateful.
This probes the boundary found in the catalogue benchmark (2/10 one-shot).
"""
import time

from chipflow import flow, model as M, ports as P, refsim, unique as U

REPAIRS = 2


class UpCounter4:
    def reset(self):
        self.q = 0

    def step(self, i):
        if i.get("en"):
            self.q = (self.q + 1) & 0xF
        return {"q": self.q}


class ShiftReg4:
    def reset(self):
        self.q = 0

    def step(self, i):
        if i.get("en"):
            self.q = ((self.q << 1) | (i["din"] & 1)) & 0xF
        return {"q": self.q}


class PulseDetect:
    def reset(self):
        self.prev = 0

    def step(self, i):
        d = i["d"] & 1
        pulse = d & (1 - self.prev)
        self.prev = d
        return {"pulse": pulse}


class SeqDet101:
    def reset(self):
        self.hist = 0

    def step(self, i):
        self.hist = ((self.hist << 1) | (i["din"] & 1)) & 0b111
        return {"found": 1 if self.hist == 0b101 else 0}


DESIGNS = [
    {
        "top": "upcounter4",
        "spec": "A 4-bit up counter with synchronous reset and an enable. "
                "On each clock, if en is high q increments by 1 and wraps "
                "from 15 to 0; if en is low q holds.",
        "ports": ["clk: input, width 1", "rst: input, width 1",
                  "en: input, width 1", "q: output, width 4"],
        "ref": UpCounter4,
        "stim": [{"en": 1}] * 20 + [{"en": 0}] * 3 + [{"en": 1}] * 25,
        "clocked": True,
    },
    {
        "top": "shiftreg4",
        "spec": "A 4-bit serial-in parallel-out shift register with an "
                "enable. When en is high, on each clock q shifts left by one "
                "and din enters at bit 0; when en is low q holds.",
        "ports": ["clk: input, width 1", "rst: input, width 1",
                  "en: input, width 1", "din: input, width 1",
                  "q: output, width 4"],
        "ref": ShiftReg4,
        "stim": ([{"en": 1, "din": d} for d in [1, 0, 1, 1, 0, 0, 1, 0]]
                 + [{"en": 0, "din": 0}] * 2
                 + [{"en": 1, "din": d} for d in [1, 1, 0, 1, 0, 1, 0, 0]]),
        "clocked": True,
    },
    {
        "top": "pulse_detect",
        "spec": "A rising-edge detector. Output pulse is high for exactly one "
                "clock cycle when d goes from 0 to 1, and low otherwise.",
        "ports": ["clk: input, width 1", "rst: input, width 1",
                  "d: input, width 1", "pulse: output, width 1"],
        "ref": PulseDetect,
        "stim": [{"d": v} for v in
                 [0, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1]],
        "clocked": True,
    },
    {
        "top": "seqdet101",
        "spec": "An overlapping sequence detector for the pattern 101. Output "
                "found is high on the clock cycle where the most recent three "
                "input bits are 101, and low otherwise.",
        "ports": ["clk: input, width 1", "rst: input, width 1",
                  "din: input, width 1", "found: output, width 1"],
        "ref": SeqDet101,
        "stim": [{"din": b} for b in
                 [1, 0, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1]],
        "clocked": True,
    },
]


def run_one(d):
    top = d["top"]
    t0 = time.time()
    gen = M.generate_rtl(d["spec"], top, ports=d["ports"],
                         model=M.NEBIUS_MODEL)
    if not gen.get("ok"):
        return {"top": top, "ok": False, "why": "generation", "rounds": 0,
                "secs": round(time.time() - t0, 1)}
    rtl = M._normalise(gen["rtl"], top)
    ports = P.ports_of(rtl, top)
    ref = d["ref"]()
    ref.reset()
    vectors = [(dict(s), ref.step(s)) for s in d["stim"]]
    tb, checks = refsim.build_tb(top, ports, vectors, clocked=d["clocked"])

    rep = flow.build_design("seq_" + top, rtl, tb, top=top)
    rounds = 0
    while not rep.get("ok") and rounds < REPAIRS:
        rounds += 1
        fx = M.repair_rtl(rtl, top, U._error_for_repair(rep),
                          model=M.NEBIUS_MODEL, tb=tb)
        if not fx.get("ok") or not fx.get("rtl"):
            break
        rtl = M._normalise(fx["rtl"], top)
        rep = flow.build_design("seq_" + top, rtl, tb, top=top)

    why = ""
    if not rep.get("ok"):
        for k, v in (rep.get("stages") or {}).items():
            if isinstance(v, dict) and not v.get("ok") and v.get("errors"):
                why = f"{k}: {str(v['errors'][0]).strip()[:90]}"
                break
    return {"top": top, "ok": bool(rep.get("ok")), "why": why,
            "rounds": rounds, "secs": round(time.time() - t0, 1)}


def main():
    print(f"model: {M.NEBIUS_MODEL}  provider: {M.provider()}")
    print(f"designs: {len(DESIGNS)} sequential  repairs: {REPAIRS}\n")
    rows = []
    for d in DESIGNS:
        r = run_one(d)
        rows.append(r)
        print(f"  {r['top']:14s} {'PASS' if r['ok'] else 'FAIL'} "
              f"{r['secs']:6.1f}s repairs={r['rounds']} {r['why'][:70]}")
    n = sum(1 for r in rows if r["ok"])
    print(f"\n{'='*50}")
    print(f"SEQUENTIAL DESIGNS: {n}/{len(rows)} passed the full gate")
    print(f"one-shot passes: "
          f"{sum(1 for r in rows if r['ok'] and r['rounds'] == 0)}")


if __name__ == "__main__":
    main()
