"""Tests for the knowledge subsystem (offline, deterministic)."""
import os
import tempfile

os.environ["COAL_LEARN_NO_LLM"] = "1"

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
    from knowledge import (compression, curriculum, mechanics, mind, reader,
                           router, skill, speed)

    print("== 1. router (bandit) ==")
    r = router.choose()
    ok("choose returns a route", r in router.ROUTES)
    router.update("semantic", 1.0)
    router.update("keyword", 0.0)
    st = router.stats()
    ok("stats track pulls", st["total"] >= 2)
    res = router.retrieve("anything", k=2, route="recency")
    ok("retrieve has route", res["route"] == "recency")

    print("== 2. mechanics (indexing schemes) ==")
    samples = ["the quick brown fox jumps over the lazy dog " * 8,
               "hash tables map keys to buckets using a hash function " * 8]
    queries = ["hash function buckets", "quick brown fox"]
    exp = mechanics.experiment(samples, queries)
    ok("scheme scores present", len(exp["schemes"]) >= 3)
    ok("best is a scheme", exp["best"] in mechanics.SCHEMES)
    ok("best() returns int", isinstance(mechanics.best(), int))

    print("== 3. reader ==")
    d = tempfile.mkdtemp()
    p = os.path.join(d, "note.txt")
    open(p, "w", encoding="utf-8").write("Coal reader test content")
    ok("reads file", "reader test" in reader.read_source(p))
    ok("empty on missing", reader.read_source(os.path.join(d, "nope")) == "")

    print("== 4. speed (cache) ==")
    speed.clear()
    calls = {"n": 0}

    def fake(q, k):
        calls["n"] += 1
        return {"route": "semantic", "hits": [1], "n": 1}
    a = speed.cached_retrieve("cached query", 3, fn=fake)
    b = speed.cached_retrieve("cached query", 3, fn=fake)
    ok("miss then hit", a["cached"] is False and b["cached"] is True)
    ok("fn called once", calls["n"] == 1)
    ok("hit_rate > 0", speed.stats()["hit_rate"] > 0)

    print("== 5. skills ==")
    path = skill.add("demo_skill", "# Demo\nstep 1")
    ok("skill written", os.path.exists(path))
    ok("skill listed", "demo_skill.md" in skill.list_skills())
    ok("skill read", "step 1" in skill.get("demo_skill"))

    print("== 6. compression stats ==")
    ok("compression stats dict",
       isinstance(compression.stats(), dict))

    print("== 7. curriculum ==")
    ok("sequence is list", isinstance(curriculum.sequence(n=3), list))

    print("== 8. facade ==")
    ok("mind.stats keys",
       set(mind.stats()) >= {"router", "speed", "compression", "skills"})

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
