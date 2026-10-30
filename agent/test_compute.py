"""Tests for the Coal-Compute accelerator layer."""
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
    import compute

    print("== 1. discovery ==")
    av = compute.available()
    ok("available has worker key", "worker" in av)
    ok("priority order sane",
       av["priority"][0] == "directml" and av["priority"][-1] == "cpu")

    print("== 2. model ladder ==")
    mp = compute.models_present()
    ok("models_present is a dict", isinstance(mp, dict))
    ok("ladder falls back to procedural",
       compute.MODEL_LADDER[-1] == "procedural")
    pm = compute.pick_model()
    ok("pick_model returns a ladder entry",
       pm in compute.MODEL_LADDER or pm in compute.CANDIDATE_MODELS)
    ok("pick_model with unknown prefer still safe",
       compute.pick_model("does-not-exist") in
       (compute.MODEL_LADDER + compute.CANDIDATE_MODELS))

    print("== 3. worker probe (needs the ML venv) ==")
    if av.get("venv"):
        p = compute.probe()
        ok("probe ok", p.get("ok") is True)
        ok("cpu provider always present",
           "CPUExecutionProvider" in p.get("providers", []))
        if "DmlExecutionProvider" in p.get("providers", []):
            print("  [info] DirectML available")
    else:
        print("  [skip] ML venv not installed")

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
