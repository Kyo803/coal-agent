"""Tests for the Memory Mediator (Structure 2)."""
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
    from memory import mediator

    print("== 1. snapshot ==")
    s = mediator.snapshot()
    ok("snapshot keys", {"free_ram_gb", "server_up", "ollama_loaded"}
       <= set(s))
    ok("ram float", isinstance(s["free_ram_gb"], float))

    print("== 2. plan ==")
    p = mediator.plan("build")
    ok("plan keys", {"phase", "snapshot", "actions"} <= set(p))
    ok("actions are list", isinstance(p["actions"], list))
    ok("action shape", all("action" in a for a in p["actions"]))
    ok("phase preserved", p["phase"] == "build")

    print("== 3. apply (no-op safe) ==")
    r = mediator.apply([])
    ok("applies empty", r == {"done": []})

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)