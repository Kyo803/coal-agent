"""Nemotron chip battery: six NOVEL designs (not in the 50-design catalogue).

Each design gets:
  * a specification + exact port list given to the model
  * a Python reference model written independently of the RTL
  * a testbench generated from that model (the model never sees it)
  * the full gate: lint -> sim -> synth -> formal -> PnR
  * up to 2 repairs, where the model is shown the gate's error text

A pass means the model's RTL matches the specification, not itself.
"""
import time

from chipflow import flow, model as M, ports as P, refsim, unique as U

REPAIRS = 2


# --- reference models (the oracle; written from the spec, not the RTL) ------
class Bin2Gray:
    def reset(self):
        pass

    def step(self, i):
        b = i["b"] & 0xF
        return {"g": (b ^ (b >> 1)) & 0xF}


class Popcount6:
    def reset(self):
        pass

    def step(self, i):
        return {"cnt": bin(i["a"] & 0x3F).count("1")}


class Min3:
    def reset(self):
        pass

    def step(self, i):
        return {"y": min(i["a"] & 0xF, i["b"] & 0xF, i["c"] & 0xF)}


class Majority3:
    def reset(self):
        pass

    def step(self, i):
        a, b, c = i["a"] & 1, i["b"] & 1, i["c"] & 1
        return {"y": (a & b) | (b & c) | (a & c)}


class Thermometer:
    def reset(self):
        pass

    def step(self, i):
        x = i["x"] & 7
        return {"t": (1 << x) - 1}


class Palindrome:
    def reset(self):
        pass

    def step(self, i):
        d = i["d"] & 0xFF
        r = int(f"{d:08b}"[::-1], 2)
        return {"pal": 1 if d == r else 0}


DESIGNS = [
    {
        "top": "bin2gray4",
        "spec": "A 4-bit binary-to-Gray converter, combinational. Input b[3:0] "
                "is binary; output g[3:0] is its Gray code (g = b ^ (b>>1)).",
        "ports": ["b: input, width 4", "g: output, width 4"],
        "ref": Bin2Gray,
        "stim": [{"b": x} for x in range(16)],
    },
    {
        "top": "popcount6",
        "spec": "A 6-bit population counter, combinational. Input a[5:0]; "
                "output cnt[2:0] is the number of 1 bits in a (0..6).",
        "ports": ["a: input, width 6", "cnt: output, width 3"],
        "ref": Popcount6,
        "stim": [{"a": x} for x in range(64)],
    },
    {
        "top": "min3_4bit",
        "spec": "A 3-input unsigned minimum, combinational. Inputs a,b,c are "
                "4-bit unsigned; output y is the smallest of the three.",
        "ports": ["a: input, width 4", "b: input, width 4",
                  "c: input, width 4", "y: output, width 4"],
        "ref": Min3,
        "stim": [{"a": a, "b": b, "c": c} for a in range(16)
                 for b in range(16) for c in range(0, 16, 3)],
    },
    {
        "top": "majority3",
        "spec": "A 3-input majority voter, combinational. Output y is 1 when "
                "at least two of a, b, c are 1.",
        "ports": ["a: input, width 1", "b: input, width 1",
                  "c: input, width 1", "y: output, width 1"],
        "ref": Majority3,
        "stim": [{"a": a, "b": b, "c": c} for a in (0, 1)
                 for b in (0, 1) for c in (0, 1)],
    },
    {
        "top": "thermometer3to7",
        "spec": "A 3-to-7 thermometer decoder, combinational. Input x[2:0]; "
                "output t[6:0] has the lowest x bits set to 1 and the rest 0 "
                "(x=0 -> 0000000, x=7 -> 1111111).",
        "ports": ["x: input, width 3", "t: output, width 7"],
        "ref": Thermometer,
        "stim": [{"x": x} for x in range(8)],
    },
    {
        "top": "palindrome8",
        "spec": "An 8-bit bit-palindrome detector, combinational. Output pal "
                "is 1 when d[7:0] reads the same forwards and backwards "
                "(bit 7 equals bit 0, bit 6 equals bit 1, etc.).",
        "ports": ["d: input, width 8", "pal: output, width 1"],
        "ref": Palindrome,
        "stim": [{"d": x} for x in range(256)],
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
    tb, checks = refsim.build_tb(top, ports, vectors, clocked=False)

    rep = flow.build_design("novel_" + top, rtl, tb, top=top)
    rounds = 0
    while not rep.get("ok") and rounds < REPAIRS:
        rounds += 1
        fx = M.repair_rtl(rtl, top, U._error_for_repair(rep),
                          model=M.NEBIUS_MODEL, tb=tb)
        if not fx.get("ok") or not fx.get("rtl"):
            break
        rtl = M._normalise(fx["rtl"], top)
        rep = flow.build_design("novel_" + top, rtl, tb, top=top)

    why = ""
    if not rep.get("ok"):
        for k, v in (rep.get("stages") or {}).items():
            if isinstance(v, dict) and not v.get("ok") and v.get("errors"):
                why = f"{k}: {str(v['errors'][0]).strip()[:90]}"
                break
    return {"top": top, "ok": bool(rep.get("ok")), "why": why,
            "rounds": rounds, "checks": checks,
            "secs": round(time.time() - t0, 1)}


def main():
    print(f"model: {M.NEBIUS_MODEL}  provider: {M.provider()}")
    print(f"designs: {len(DESIGNS)} novel  repairs allowed: {REPAIRS}\n")
    rows = []
    for d in DESIGNS:
        r = run_one(d)
        rows.append(r)
        tag = "PASS" if r["ok"] else "FAIL"
        print(f"  {r['top']:16s} {tag} {r['secs']:6.1f}s "
              f"repairs={r['rounds']} {r['why'][:70]}")
    n = sum(1 for r in rows if r["ok"])
    print(f"\n{'='*50}")
    print(f"NOVEL DESIGNS: {n}/{len(rows)} passed the full gate")
    print(f"one-shot passes: "
          f"{sum(1 for r in rows if r['ok'] and r['rounds'] == 0)}")
    return 0 if n == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
