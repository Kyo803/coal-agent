"""Tests for the MoE Expert Engine (Structure 1)."""
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
    import os

    from moe import bench, inventory, placement, presets
    from coal_config import cfg

    # the 35B GGUF lives on an external drive; do not fail the suite just
    # because that drive is unplugged.
    mp = cfg.model_path() or ""
    drive = os.path.splitdrive(mp)[0]
    if drive and not os.path.isdir(drive + os.sep):
        print("== 1. inventory ==")
        print(f"  [skip] model drive {drive} is not connected ({mp})")
        print("=" * 40)
        print("0 passed, 0 failed (skipped)")
        return 0

    print("== 1. inventory ==")
    inv = inventory.load()
    st = inventory.stats(inv)
    ok("manifest has tensors", st["tensors"] > 700)
    ok("experts dominate", st["exps_share"] > 0.5)
    ok("dense is small", st["dense_gb"] < 3.0)
    ok("classify exps", inventory.classify("blk.3.ffn_up_exps.weight")[1]
       == "exps")
    ok("classify shexp", inventory.classify("blk.1.ffn_up_shexp.weight")[1]
       == "shexp")
    ok("classify router", inventory.classify("blk.2.ffn_gate_inp.weight")[1]
       == "router")

    print("== 2. placement ==")
    args = placement.placement_args()
    ok("has -ot", "-ot" in args)
    ok("uses Vulkan0", any("Vulkan0" in a for a in args))
    feas = placement.feasibility()
    ok("fits 8GB", feas["fits_8gb"] is True)

    print("== 3. presets ==")
    ok("has names", {"chat", "cpu", "moe_resident", "chip"} <=
       set(presets.names()))
    ok("resolve chat is list", isinstance(presets.resolve("chat"), list))
    ok("resolve moe_resident is list",
       isinstance(presets.resolve("moe_resident"), list))

    print("== 4. bench primitives ==")
    fr = bench.free_ram_gb()
    ok("free ram float", fr > 0.0)
    ok("rss is int", isinstance(bench.server_rss_mb(), int))

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)