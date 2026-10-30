"""Tests for the self-improvement subsystem (no apply, no full suites)."""
import os

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
    from selfimprove import (genome, hypothesis, observer, policy, predictor,
                             proposer, scoreboard, validator, applier)
    from selfimprove import experiments

    print("== 1. scoreboard ==")
    b = {"passed": 200, "failed": 0}
    ok("score all-pass", scoreboard.score(b) == 200)
    ok("score penalises failures",
       scoreboard.score({"passed": 10, "failed": 2}) == 0)
    cmp = scoreboard.compare({"passed": 200, "failed": 0},
                             {"passed": 190, "failed": 0})
    ok("compare better", cmp["better"] and cmp["delta"] > 0)
    cmp2 = scoreboard.compare({"passed": 100, "failed": 3},
                              {"passed": 200, "failed": 0})
    ok("compare worse -> not better", not cmp2["better"])
    ok("no new failures flag", not cmp2["no_new_failures"])

    print("== 2. genome ==")
    files = genome.scan()
    ok("scan finds core files", len(files) > 5)
    ok("genome id stable", genome.genome_id(files) == genome.genome_id(files))
    d = genome.diff({"files": {"a.py": "1", "b.py": "2"}},
                    {"files": {"a.py": "X", "c.py": "3"}})
    ok("diff detects change", d["changed"] == ["a.py"])
    ok("diff detects add/remove", d["added"] == ["c.py"]
       and d["removed"] == ["b.py"])

    print("== 3. policy ==")
    seed_h = {"kind": "seed", "target": "config:seed_topics"}
    ok("dry-run wins",
       policy.decide(seed_h, dry_run=True)["action"] == "dry_run")
    ok("low-risk applies",
       policy.decide(seed_h, dry_run=False)["action"] == "apply")
    tool_h = {"kind": "tool", "target": "tools/specs.py"}
    ok("tool needs experiment",
       policy.decide(tool_h, dry_run=False)["action"] == "experiment")
    core_h = {"kind": "code", "target": "coal.py"}
    ok("core refused without opt-in",
       policy.decide(core_h, dry_run=False)["action"] == "refuse")
    ok("core experiments with opt-in",
       policy.decide(core_h, dry_run=False,
                     allow_high_risk=True)["action"] == "experiment")

    print("== 4. predictor ==")
    p = predictor.predict(core_h)
    ok("predict risk/scope", p["risk"] >= 3 and p["scope"] == "core")

    print("== 5. validator ==")
    ok("py syntax ok", validator.validate_content("x.py", "a = 1")[0])
    ok("py syntax bad", not validator.validate_content("x.py", "def (")[0])
    ok("json ok", validator.validate_content("x.json", "{}")[0])
    ok("json bad", not validator.validate_content("x.json", "{")[0])

    print("== 6. hypothesis + proposer ==")
    hyps = hypothesis.from_signals([{"kind": "learning_stalled",
                                     "weight": 1.0, "detail": "x"}])
    ok("hypothesis built", len(hyps) == 1 and hyps[0]["kind"] == "seed")
    prop = proposer.propose(hyps[0], llm_ok=False)
    ok("seed proposal", prop is not None and prop["kind"] == "seed")
    ok("seed proposal validates",
       validator.validate_change(prop)[0] if prop else False)

    print("== 7. observer ==")
    sigs = observer.collect()
    ok("collect returns list", isinstance(sigs, list))

    print("== 8. experiment (isolated copy) ==")
    exp = experiments.run({"kind": "seed", "topics": ["x"]}, suites=[])
    ok("experiment returns dict", isinstance(exp, dict) and "passed" in exp)
    ok("experiment copied core", exp["board"]["passed"] == 0)

    print("== 9. applier dry-run is a no-op ==")
    r = applier.apply({"kind": "seed", "topics": ["x"]}, dry_run=True)
    ok("applier dry-run ok", r.get("ok") and r.get("dry_run"))

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
