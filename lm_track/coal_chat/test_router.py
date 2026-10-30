"""Tests for the Task-Specialization Router (Structure 3)."""
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
    from specialization import classify, route
    from specialization.registry import FAMILIES

    print("== 1. classification ==")
    ok("verilog -> chip", classify("build a 16-bit cpu in verilog") == "chip")
    ok("hdl -> chip", classify("write an RTL testbench for an ALU") == "chip")
    ok("python -> code", classify("write a python script that reads csv")
       == "code")
    ok("npm -> code", classify("npm install and build the vite app") == "code")
    ok("long -> long_doc", classify("summarize this long document") ==
       "long_doc")
    ok("default chat", classify("how are you?") == "chat")

    print("== 2. route payload ==")
    cfg = route("create a verilog FIFO with a testbench")
    ok("chip family", cfg["family"] == "chip")
    ok("chip mode", cfg["mode"] == "hdl_gates")
    ok("has overlay", bool(cfg["overlay"]))
    ok("server profile is string", isinstance(cfg["profile"], str))

    print("== 3. families keys ==")
    needed = {"keywords", "mode", "server_profile", "overlay"}
    ok("every family complete",
       all(needed <= set(v) for v in FAMILIES.values()))
    ok("chat default", route("hi")["family"] == "chat")

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)