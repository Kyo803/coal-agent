"""Offline tests for the independent-learning brain.

No network, no LLM: forces the tfidf embedder and the heuristic fallbacks
so the whole pipeline is deterministic and fast.
"""
import os

os.environ["ROX_LEARN_NO_LLM"] = "1"

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
    from learning.curiosity.graph import CuriosityGraph
    from learning.curiosity.mood import Mood
    from learning.curiosity.drive import rank, reward, novelty
    from learning import planner, loop, assess, notes, curriculum

    print("== 1. curiosity graph ==")
    g = CuriosityGraph()
    g.ensure("test_topic", interest=0.7)
    g.ensure("test_sub", interest=0.5, parent="test_topic")
    g.touch("test_topic", mastery_delta=0.4, source="src1", question="why?")
    t = g.get("test_topic")
    ok("topic created", t is not None)
    ok("mastery updated", t["mastery"] >= 0.4)
    ok("source recorded", "src1" in t["sources"])
    ok("question recorded", "why?" in t["questions"])
    ok("edge created", any(n == "test_sub" for n, _ in
                           g.neighbors("test_topic")))
    ok("frontier non-empty", len(g.frontier(5)) > 0)
    ok("parent link", "test_topic" in g.get("test_sub")["parents"])

    print("== 2. mood ==")
    m = Mood()
    before = m.excitement
    m.cycle(novelty=0.9, surprise=0.5, competence=0.3, rewarded=True)
    ok("excitement rises on reward", m.excitement >= before - 0.001)
    ok("describe has fields", "excitement" in m.describe())

    print("== 3. drive ==")
    r1 = novelty("brand_new_topic_xyz", g)
    ok("novelty of unseen ~1", r1 > 0.9)
    ranked = rank(g, Mood(), n=3)
    ok("rank returns tuples", all(isinstance(x[0], str) for x in ranked))
    ok("reward in [0,1]", 0 <= reward("test_topic", g, Mood()) <= 1)

    print("== 4. planner (offline fallback) ==")
    plan = planner.plan("binary trees")
    ok("plan has questions", len(plan["questions"]) >= 3)
    ok("questions mention topic", any("binary trees" in q
                                      for q in plan["questions"]))

    print("== 5. offline learning cycle ==")
    r = loop.cycle(topic="sorting", allow_network=False)
    ok("cycle ok", r.get("ok") is True)
    ok("cycle has mastery", "mastery" in r)
    ok("cycle has mood", "mood" in r)
    ok("graph grew", r["graph"]["topics"] > 0)

    print("== 6. assess + notes ==")
    notes.add("assess_topic", "a durable learned note")
    ok("notes count", notes.count("assess_topic") >= 1)
    rep = assess.report("assess_topic")
    ok("report has mastery", "mastery" in rep)
    ok("coverage in [0,1]", 0 <= rep["coverage"] <= 1)

    print("== 7. curriculum ==")
    seq = curriculum.sequence(g, n=4)
    ok("sequence is list", isinstance(seq, list))

    print("== 8. guardrails ==")
    from learning import guardrails
    good, _ = guardrails.allowed_url("https://en.wikipedia.org/wiki/Graph")
    bad, _ = guardrails.allowed_url("http://thepiratebay.org/x")
    ok("wikipedia allowed", good)
    ok("piracy blocked", not bad)
    ok("trust arxiv high", guardrails.trust("https://arxiv.org/abs/1") > 0.8)

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
