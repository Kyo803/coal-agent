"""Verify Coal owns the build: branded GGUF + manifest + notices."""
import json
import os

import numpy as np

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
    from coal_config import cfg

    print("== 1. config points at the Coal build ==")
    mp = cfg.model_path() or ""
    ok("gguf path is Coal build", "Coal" in mp or "Coal" in mp)
    ok("base_model recorded", cfg.model.get("base_model") ==
       "Qwen/Qwen3.6-35B-A3B")

    print("== 2. manifest ==")
    man = os.path.join(cfg.install_dir, "models", "variants",
                       "coaln_manifest.json")
    ok("manifest exists", os.path.exists(man))
    d = json.load(open(man, encoding="utf-8")) if os.path.exists(man) else {}
    ok("weights bit-identical", "bit-identical" in d.get("weights", ""))
    ok("has source+build sha", bool(d.get("source_sha256")) and
       bool(d.get("built_sha256")))
    ok("license apache", d.get("license") == "apache-2.0")

    print("== 3. GGUF identity ==")
    if os.path.exists(mp):
        from gguf import GGUFReader
        r = GGUFReader(mp)

        def g(k):
            f = r.fields.get(k)
            if not f:
                return None
            v = f.contents()
            if isinstance(v, np.ndarray) and v.dtype == np.uint8:
                return bytes(v).decode("utf-8", "replace")
            if (isinstance(v, (list, tuple)) and v
                    and isinstance(v[0], np.ndarray)
                    and v[0].dtype == np.uint8):
                return bytes(v[0]).decode("utf-8", "replace")
            return v[0] if isinstance(v, (list, tuple)) and len(v) == 1 else v
        ok("name branded", g("general.name") == "Coal 35B A3B")
        ok("author Coal", g("general.author") == "Coal")
        ok("license field", str(g("general.license")).startswith("apache"))
        ok("base recorded in file", "Qwen3.6-35B-A3B" in
           str(g("general.base_model")))
        ok("tensor count 733", len(r.tensors) == 733)
    else:
        d = os.path.splitdrive(mp)[0]
        if d and not os.path.isdir(d + os.sep):
            print(f"  [skip] model drive {d} is not connected "
                  f"- GGUF identity checks skipped")
        else:
            ok("branded gguf present", False)

    print("== 4. ownership artifacts ==")
    for fn in ("MODEL_CARD.md", "NOTICE.md"):
        ok(f"{fn} exists", os.path.exists(fn))

    print("== 5. chip domain branded ==")
    from specialization import route
    ok("Silicon Lab overlay", "Silicon Lab" in
       route("verilog cpu").get("overlay", ""))

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)