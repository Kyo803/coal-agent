"""Board tool handlers: let Coal query its own detective board.

The board is attached to the execution context by coal.py (ctx.board).
All handlers degrade gracefully if the board is unavailable.
"""
from __future__ import annotations

import json


def _board(ctx):
    return getattr(ctx, "board", None)


def board_search(args, ctx):
    b = _board(ctx)
    if b is None:
        return {"ok": False, "output": "board unavailable"}
    q = args.get("query", "")
    limit = int(args.get("limit", 8))
    hits = b.search_text(q, limit=limit)
    nodes = b.top_nodes(limit=limit)
    lines = []
    seen = set()
    for h in hits:
        if h["card_type"] == "node":
            n = b.get_node_by_id(h["card_id"])
            if n and n["id"] not in seen:
                seen.add(n["id"])
                lines.append(f"- [{n['kind']}] {n['name']}"
                             + (f": {n['summary'][:100]}" if n.get("summary")
                                else ""))
        elif h["card_type"] == "dossier":
            d = b.get_dossier(h["card_id"])
            if d:
                lines.append(f"- conversation \"{d['title']}\": "
                             f"{(d.get('summary') or '')[:140]}")
    if not lines:
        # fall back to name match
        toks = [t for t in q.lower().split() if len(t) > 2]
        for n in nodes:
            if any(t in n["name"].lower() for t in toks):
                lines.append(f"- [{n['kind']}] {n['name']}")
    return {"ok": True, "output": "\n".join(lines[:limit]) or
            "nothing on the board for that"}


def board_entity(args, ctx):
    b = _board(ctx)
    if b is None:
        return {"ok": False, "output": "board unavailable"}
    name = args.get("name", "")
    n = b.get_node(name)
    if not n:
        return {"ok": True, "output": f"no board entity matches '{name}'"}
    out = [f"[{n['kind']}] {n['name']}"]
    if n.get("summary"):
        out.append(n["summary"])
    for nb in b.neighbors(n["id"])[:10]:
        arrow = "-->" if nb["dir"] == "out" else "<--"
        out.append(f"  {arrow} {nb['relation']} {nb['name']} ({nb['kind']})")
    prov = b.provenance_for("node", n["id"], limit=2)
    if prov:
        th = (prov[0].get("thinking") or "").strip()
        if th:
            out.append(f"  Coal thought: {th[:300]}")
    return {"ok": True, "output": "\n".join(out)}


def board_related(args, ctx):
    b = _board(ctx)
    if b is None:
        return {"ok": False, "output": "board unavailable"}
    n = b.get_node(args.get("name", ""))
    if not n:
        return {"ok": True, "output": "entity not found"}
    ns = b.neighbors(n["id"])
    if not ns:
        return {"ok": True, "output": f"{n['name']} has no relations yet"}
    return {"ok": True, "output": "\n".join(
        f"- {n['name']} {nb['relation']} {nb['name']}" for nb in ns[:20])}


def board_timeline(args, ctx):
    b = _board(ctx)
    if b is None:
        return {"ok": False, "output": "board unavailable"}
    limit = int(args.get("limit", 15))
    evs = b.timeline(limit=limit)
    if not evs:
        return {"ok": True, "output": "timeline is empty"}
    import time as _t
    return {"ok": True, "output": "\n".join(
        f"- [{e['kind']}] {_t.strftime('%Y-%m-%d', _t.localtime(e['ts']))} "
        f"{e['text'][:160]}" for e in evs)}


def board_dossier(args, ctx):
    b = _board(ctx)
    if b is None:
        return {"ok": False, "output": "board unavailable"}
    sid = args.get("session_id")
    d = b.get_dossier(int(sid)) if sid is not None else \
        (b.recent_dossiers(limit=1) or [None])[0]
    if not d:
        return {"ok": True, "output": "no dossier found"}
    out = [f"Dossier: {d['title']}", d.get("summary") or ""]
    for key in ("topics", "decisions", "tasks", "questions"):
        if d.get(key):
            out.append(f"  {key}: " + "; ".join(
                str(x)[:80] for x in d[key][:6]))
    return {"ok": True, "output": "\n".join(x for x in out if x)}


def board_show(args, ctx):
    """Return the full openable card (incl. Coal's reasoning) as JSON."""
    b = _board(ctx)
    if b is None:
        return {"ok": False, "output": "board unavailable"}
    from board.export import node_card, dossier_card
    ctype = (args.get("card_type") or "node").lower()
    cid = args.get("card_id")
    if cid is None and args.get("name"):
        n = b.get_node(args["name"])
        cid = n["id"] if n else None
    if cid is None:
        return {"ok": False, "output": "need card_id or name"}
    cid = int(cid)
    card = dossier_card(b, cid) if ctype == "dossier" else node_card(b, cid)
    if not card:
        return {"ok": True, "output": "card not found"}
    return {"ok": True, "output": json.dumps(card, indent=1)[:4000]}


def board_stats(args, ctx):
    b = _board(ctx)
    if b is None:
        return {"ok": False, "output": "board unavailable"}
    return {"ok": True, "output": json.dumps(b.stats())}


def board_archive(args, ctx):
    """Queue is drained by the runtime; report how many are pending."""
    b = _board(ctx)
    if b is None:
        return {"ok": False, "output": "board unavailable"}
    try:
        import os
        from board.queue import Queue
        root = getattr(ctx, "memory_root", None) or \
            os.path.expanduser("~/.coal")
        n = Queue(root).count()
        return {"ok": True, "output": f"{n} exchanges pending archive "
                f"(run `python coal.py --archive` to build the board)"}
    except Exception as e:
        return {"ok": False, "output": f"queue error: {e}"}
