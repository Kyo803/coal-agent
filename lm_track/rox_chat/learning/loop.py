"""The learning cycle — the autonomous loop that makes ROX N grow.

One cycle:
  1. pick a topic from the curiosity frontier (or use the one asked for)
  2. plan it (subtopics + questions)
  3. discover sources and ingest them into RAG + notes
  4. rehearse (answer its own questions; self-score)
  5. synthesize a distilled understanding
  6. update mastery in the graph, open subtopics, detect surprise
  7. update the mood (eagerness/boredom) and journal the cycle

Everything is local-first and degrades gracefully offline.
"""
from __future__ import annotations

from rox_config import cfg

from . import (assess, curriculum, ingest, notes, paths, planner, rehearse,
               sources, synthesize)
from .curiosity import drive, plans, surprise
from .curiosity.graph import CuriosityGraph
from .curiosity.mood import Mood

_DEFAULT_SEEDS = [
    "mathematics", "physics", "computer science", "algorithms",
    "machine learning", "systems programming", "electronics",
    "digital design", "web engineering", "software architecture",
]


def _lc():
    return cfg.get("learning", {}) or {}


def _rag_context(topic, k=4):
    try:
        return ingest.rag().context(topic, k=k) or ""
    except Exception:
        return ""


def ensure_seeded(graph=None) -> int:
    g = graph or CuriosityGraph()
    seeds = _lc().get("seed_topics") or _DEFAULT_SEEDS
    return g.seed(seeds, interest=0.6)


def choose_topic(graph=None, mood=None) -> str | None:
    g = graph or CuriosityGraph()
    m = mood or Mood()
    ensure_seeded(g)
    ranked = drive.rank(g, m, n=1)
    return ranked[0][0] if ranked else None


def cycle(topic: str | None = None, allow_network: bool | None = None,
          budget: int | None = None) -> dict:
    lc = _lc()
    if allow_network is None:
        allow_network = bool(lc.get("allow_network", True))
    kinds = tuple(lc.get("source_kinds",
                         ["encyclopedia", "paper", "repo"]))

    g = CuriosityGraph()
    mood = Mood()
    ensure_seeded(g)

    if not topic:
        topic = choose_topic(g, mood)
    if not topic:
        return {"ok": False, "reason": "no topic available"}

    before = float((g.get(topic) or {}).get("mastery", 0.0))
    novelty = drive.novelty(topic, g)

    # 1-2. plan
    context = _rag_context(topic)
    plan = planner.plan(topic, context)

    # 3. discover + ingest
    found = sources.discover(topic, kinds) if allow_network else []
    n_src = budget if budget is not None else mood.effort()
    ing = ingest.ingest_sources(topic, found, limit=max(1, n_src))

    # 4. rehearse
    qs = plan.get("questions") or []
    rr = rehearse.rehearse(topic, qs) if qs else {"avg": 0.0, "items": []}

    # 5. synthesize
    syn = synthesize.synthesize(topic) if notes.count(topic) >= 2 else ""

    # 6. assess + graph updates
    mastery = assess.mastery(topic, rehearsal=rr["avg"])
    delta = max(0.0, mastery - before)
    g.touch(topic, mastery_delta=delta * 0.5 if ing["sources"] else 0.02,
            interest_delta=0.02)
    for sub in plan.get("subtopics", []):
        g.ensure(sub, interest=0.55, parent=topic)
    # store questions on the topic (single write)
    t = g.get(topic)
    if t is not None:
        for q in qs:
            if q not in t["questions"]:
                t["questions"].append(q)
        t["questions"] = t["questions"][-50:]
        g.save()

    # 6b. record on the detective board (structured memory)
    try:
        from . import board_bridge as _bb
        _bb.record_cycle(topic, mastery=mastery, summary=syn or "",
                         sources=[s.get("url") or s.get("title")
                                  for s in found])
    except Exception:
        pass

    # 7. surprise + mood + plan
    sur = surprise(before, rr["avg"])
    mood.cycle(novelty=novelty, surprise=sur, competence=delta,
               rewarded=bool(ing["sources"] or rr["avg"] > 0.3))
    plans.propose(g, mood)

    rec = {"ts": paths.now(), "topic": topic, "mastery": mastery,
           "delta": round(delta, 4), "sources": ing["sources"],
           "chunks": ing["chunks"], "rehearse": rr["avg"],
           "surprise": round(sur, 3), "novelty": round(novelty, 3),
           "mood": mood.describe(), "synthesized": bool(syn)}
    paths.append_jsonl("journal.jsonl", rec)
    return {"ok": True, **rec, "plan": plan,
            "graph": g.stats(), "mood": mood.d}


def study(topic: str, **kw) -> dict:
    return cycle(topic=topic, **kw)


def stats() -> dict:
    g = CuriosityGraph()
    ensure_seeded(g)
    return {"graph": g.stats(), "mood": Mood().describe(),
            "notes": notes.count(), "plan": plans.current(),
            "sequence": curriculum.sequence(g, n=6)}


if __name__ == "__main__":
    import json
    print(json.dumps(stats(), indent=1))
