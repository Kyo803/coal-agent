"""Tests for the builder's deterministic core (no model, no sandbox)."""
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
    from builder import (contract, diagnoser, freezer, objectives, optimizer,
                         requirements_check, restructurer)

    print("== 1. objectives ==")
    obj = objectives.choose("a fast accessible react dashboard", stack="react")
    ok("fallback metrics present", len(obj["metrics"]) >= 3)
    ok("metrics have weights",
       all("weight" in v for v in obj["metrics"].values()))

    print("== 2. quantum-inspired optimizer ==")
    o = {"metrics": {"correctness": {"direction": "max", "weight": 1.0},
                     "size": {"direction": "min", "weight": 0.3}}}
    designs = [
        {"name": "A", "metrics": {"correctness": 0.5, "size": 100}},
        {"name": "B", "metrics": {"correctness": 0.9, "size": 200}},
        {"name": "C", "metrics": {"correctness": 0.9, "size": 50}},
        {"name": "D", "metrics": {"correctness": 0.6, "size": 60}},
    ]
    res = optimizer.optimize(designs, o)
    ok("best is C", res["best"]["name"] == "C")
    ok("pareto non-empty", len(res["pareto"]) >= 1)
    ok("probabilities ~1",
       abs(sum(res["probabilities"]) - 1.0) < 1e-6)
    ok("energies present", len(res["energies"]) == 4)

    print("== 3. contract ==")
    ts = "export function foo() {}\nexport const bar = 1;\nimport x from './x';"
    ok("ts exports", set(contract.infer_exports(ts, "ts")) == {"foo", "bar"})
    ok("ts imports", contract.infer_imports(ts, "ts") == ["./x"])
    py = "import os\ndef a():\n    pass\nclass B:\n    pass\n"
    ok("py exports", set(contract.infer_exports(py, "py")) == {"a", "B"})
    c = contract.Contract()
    c.set_unit("u.ts", exports=["foo", "bar"])
    ok("check missing", c.check_missing("u.ts", ["foo", "baz"]) == ["baz"])

    print("== 4. diagnoser ==")
    ok("ts type error",
       diagnoser.classify("src/a.ts(3,5): error TS2322: bad type")["class"]
       == "type")
    ok("py syntax",
       diagnoser.classify('File "a.py", line 2\nSyntaxError: bad')["class"]
       == "syntax")
    ok("verilog error",
       diagnoser.classify("cpu.v:10: error: bad token")["class"] == "syntax"
       and diagnoser.classify("cpu.v:10: error: x")["line"] == 10)
    ok("test failure",
       diagnoser.classify("AssertionError: expected 1")["class"]
       == "test_failure")

    print("== 5. freezer ==")
    fz = freezer.Freezer("test_build_x")
    ok("not frozen initially", not fz.is_frozen("u.ts", "abc", ["a"]))
    fz.freeze("u.ts", "abc", ["a"])
    ok("frozen same", fz.is_frozen("u.ts", "abc", ["a"]))
    ok("unfrozen on change", not fz.is_frozen("u.ts", "abcd", ["a"]))
    ok("unfrozen on iface change", not fz.is_frozen("u.ts", "abc", ["b"]))
    fz.unfreeze("u.ts")

    print("== 6. restructurer ==")
    plan = restructurer.propose([{"phase": "COMPILE", "ok": False},
                                 {"phase": "COMPILE", "ok": False}],
                                {"class": "interface"})
    ok("restructure plan", plan["action"] == "restructure"
       and len(plan["steps"]) >= 1)

    print("== 7. requirements (non-machine criteria) ==")
    r = requirements_check.check("/tmp", ["the UI looks nice"])
    ok("unchecked reported", r["unchecked"] == 1 and r["ok"] is None)

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
