"""Learning tool handlers — the independent-learning brain.

Drives ROX N's self-directed study: run a learning cycle, force a topic,
inspect progress, and answer from what it has learned.
"""
from __future__ import annotations

from learning import brain


def _fmt(r: dict) -> str:
    if not r.get("ok", True):
        return f"failed: {r.get('reason', r)}"
    parts = [f"topic: {r.get('topic')}",
             f"sources: {r.get('sources')} (chunks {r.get('chunks')})",
             f"mastery: {r.get('mastery')} (delta {r.get('delta')})",
             f"rehearse: {r.get('rehearse')}",
             f"novelty: {r.get('novelty')} surprise: {r.get('surprise')}",
             f"mood: {r.get('mood')}"]
    if r.get("plan"):
        parts.append("questions: " + "; ".join(
            r["plan"].get("questions", [])[:4]))
    if r.get("graph"):
        parts.append(f"graph: {r['graph']}")
    return "\n".join(parts)


def learn_cycle(args, ctx):
    r = brain.cycle(
        topic=args.get("topic") or None,
        allow_network=args.get("network", True),
        budget=args.get("budget"))
    return {"ok": r.get("ok", False), "output": _fmt(r)}


def learn_topic(args, ctx):
    topic = args.get("topic")
    if not topic:
        return {"ok": False, "output": "topic required"}
    r = brain.study(topic, allow_network=args.get("network", True),
                    budget=args.get("budget"))
    return {"ok": r.get("ok", False), "output": _fmt(r)}


def learn_stats(args, ctx):
    import json
    return {"ok": True, "output": json.dumps(brain.stats(), indent=1,
                                             default=str)}


def learn_report(args, ctx):
    import json
    topic = args.get("topic")
    if not topic:
        return {"ok": False, "output": "topic required"}
    return {"ok": True, "output": json.dumps(brain.report(topic), indent=1,
                                             default=str)}


def learn_url(args, ctx):
    topic = args.get("topic") or args.get("url")
    url = args.get("url")
    if not url:
        return {"ok": False, "output": "url required"}
    r = brain.learn_url(topic, url)
    return {"ok": r.get("ok", False), "output": str(r)}


def learn_ask(args, ctx):
    q = args.get("question")
    if not q:
        return {"ok": False, "output": "question required"}
    ans = brain.ask(q, topic=args.get("topic"))
    return {"ok": True, "output": ans or "(no answer from learned memory)"}
