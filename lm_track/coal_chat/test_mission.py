"""Tests for the extreme mission catalog (offline; no model/sandbox)."""
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
    from builder import build, missions
    from builder.loop import _parse_ports, _validate_code

    print("== 1. catalog ==")
    names = build.missions()
    ok("catalog >= 7", len(names) >= 7)
    stacks = {"helios-16", "meridian-16", "vision-2", "aldra-asm",
              "tess-emu", "parallax-3d", "forge-mesh"} <= set(names)
    ok("expected set present", stacks)
    ok("no dupes", len(names) == len(set(names)))

    print("== 2. load + validate ==")
    for n in names:
        s = missions.load(n)
        v, why = missions.validate(s)
        ok(f"{n} valid", v and len(s.get("manifest", [])) >= 1)

    print("== 3. parser ==")
    parsed = _parse_ports("input clk, input rst, output reg [15:0] y, inout we")
    ok("ports parsed", any(p["name"] == "y" and p["dir"] == "output"
                           for p in parsed))

    print("== 4. code validation ==")
    ok("py ok", _validate_code("x.py", "def f():\n    return 1")[0])
    ok("py bad", not _validate_code("x.py", "def (")[0])
    ok("json ok", _validate_code("x.json", "{}")[0])

    print("== 5. unknown mission ==")
    rep = build.generate_mission("does-not-exist")
    ok("unknown refused", rep.get("ok") is False)

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)