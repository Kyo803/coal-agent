"""Builder tool handlers (extreme-coding build/verify/repair loop)."""
from __future__ import annotations

import json


def builder_run(args, ctx):
    from builder import build
    name = args.get("name")
    cwd = args.get("cwd") or args.get("dir")
    if not (name and cwd):
        return {"ok": False, "output": "name and cwd required"}
    crit = args.get("criteria")
    if isinstance(crit, str):
        crit = [c for c in crit.split(",") if c.strip()]
    desc = args.get("description")
    if desc:
        rep = build.generate_project(name, cwd, desc,
                                     stack=args.get("stack") or "node",
                                     criteria=crit)
    else:
        rep = build.run(name, cwd, stack=args.get("stack"), criteria=crit,
                        polish=args.get("polish", True),
                        optimize=args.get("optimize", True))
    return {"ok": bool(rep.get("compiled")),
            "output": json.dumps(rep, indent=1, default=str)}


def builder_objectives(args, ctx):
    from builder import objectives
    desc = args.get("description") or args.get("goal") or ""
    obj = objectives.choose(desc, stack=args.get("stack"),
                            llm_ok=False)
    return {"ok": True, "output": json.dumps(obj, indent=1, default=str)}


def builder_diagnose(args, ctx):
    from builder import diagnoser
    text = args.get("output") or args.get("text") or ""
    return {"ok": True,
            "output": json.dumps(diagnoser.classify(text), indent=1)}


def builder_optimize(args, ctx):
    from builder import objectives, optimizer
    designs = args.get("designs")
    if isinstance(designs, str):
        try:
            designs = json.loads(designs)
        except Exception:
            return {"ok": False, "output": "designs must be JSON"}
    if not isinstance(designs, list):
        return {"ok": False, "output": "designs must be a JSON list"}
    obj = objectives.choose(args.get("goal", ""), stack=args.get("stack"),
                            llm_ok=False)
    res = optimizer.optimize(designs, obj)
    res.pop("pareto", None)  # keep output small; pareto count only
    return {"ok": True, "output": json.dumps(res, indent=1, default=str)}
