"""Self-improvement tool handlers (autonomous, tested, rollback-safe)."""
from __future__ import annotations

import json


def improve_run(args, ctx):
    from selfimprove import improve
    rep = improve.run(dry_run=args.get("dry_run"),
                      allow_high_risk=args.get("allow_high_risk"))
    return {"ok": True, "output": json.dumps(rep, indent=1, default=str)}


def improve_status(args, ctx):
    from selfimprove import improve
    return {"ok": True, "output": json.dumps(improve.status(), indent=1,
                                             default=str)}


def improve_signals(args, ctx):
    from selfimprove import improve
    return {"ok": True, "output": json.dumps(improve.signals(), indent=1,
                                             default=str)}


def improve_rollback(args, ctx):
    from selfimprove import improve
    path = args.get("path")
    if not path:
        return {"ok": False, "output": "path required"}
    r = improve.rollback.restore_file(path, args.get("snapshot"))
    return {"ok": r.get("ok", False), "output": json.dumps(r, default=str)}
