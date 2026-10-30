"""End-to-end chip development with Nemotron on a novel design.

Novel means: not in the 50-design catalogue, so no generator can match it and
the model is genuinely exercised. The testbench is NOT written by the model --
it is generated from a Python reference model of the specification, so a pass
means the model's RTL matches the spec.
"""
import time

from chipflow import flow, model as M, ports as P, refsim

TOP = "gray2bin"
SPEC = ("A 4-bit Gray-code to binary converter. Input g[3:0] is a Gray-code "
        "value; output b[3:0] is the corresponding binary value, "
        "combinational.")
PORTS = ["g: input, width 4", "b: output, width 4"]


class Ref:
    """Reference model of the specification (written independently of the RTL)."""

    def reset(self):
        pass

    def step(self, i):
        g = i["g"] & 0xF
        # Gray -> binary is the full XOR chain, not a single shift:
        # b = g ^ (g>>1) ^ (g>>2) ^ (g>>3)
        b = g
        b ^= b >> 1
        b ^= b >> 2
        return {"b": b & 0xF}


def main():
    print(f"model    : {M.NEBIUS_MODEL}")
    print(f"provider : {M.provider()}")

    t0 = time.time()
    gen = M.generate_rtl(SPEC, TOP, ports=PORTS, model=M.NEBIUS_MODEL)
    print(f"generate : ok={gen.get('ok')} ({round(time.time()-t0,1)}s)")
    if not gen.get("ok"):
        print("  ", gen.get("reason"))
        return 1
    rtl = M._normalise(gen["rtl"], TOP)
    print(f"  RTL {len(rtl)} chars")

    # independent testbench: exhaust every input, from the Python model
    ports = P.ports_of(rtl, TOP)
    model = Ref()
    model.reset()
    stim = [{"g": g} for g in range(16)]
    vectors = [(dict(s), model.step(s)) for s in stim]
    tb, checks = refsim.build_tb(TOP, ports, vectors, clocked=False)
    print(f"  TB  {len(tb)} chars, {checks} checks (independent reference model)")

    rep = flow.build_design("novel_gray2bin", rtl, tb, top=TOP)
    rounds = 0
    while not rep.get("ok") and rounds < 2:
        rounds += 1
        print(f"  repair {rounds}: feeding the gate's error back to the model")
        from chipflow import unique as U
        fx = M.repair_rtl(rtl, TOP, U._error_for_repair(rep),
                          model=M.NEBIUS_MODEL, tb=tb)
        if not fx.get("ok") or not fx.get("rtl"):
            print("   repair produced nothing")
            break
        rtl = M._normalise(fx["rtl"], TOP)
        rep = flow.build_design("novel_gray2bin", rtl, tb, top=TOP)

    print(f"gate     : ok={rep.get('ok')} after {rounds} repair(s)")
    for k, v in (rep.get("stages") or {}).items():
        ok = v.get("ok") if isinstance(v, dict) else bool(v)
        print(f"  {k:7s} ok={ok}")
    if not rep.get("ok"):
        for k, v in (rep.get("stages") or {}).items():
            if isinstance(v, dict) and not v.get("ok"):
                for e in (v.get("errors") or [])[:2]:
                    print(f"  [{k}] {str(e).strip()[:200]}")
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
