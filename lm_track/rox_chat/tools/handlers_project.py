"""Project awareness tool handlers: create/open/scan/status/journal/
audit/map/related. These give ROX N the "remembers everything about the
project" capability.
"""
from __future__ import annotations

import os

try:
    from project import (Project, Journal, Auditor, project_context,
                         file_context, slugify)
except ImportError:
    try:
        from ..project import (Project, Journal, Auditor, project_context,
                               file_context, slugify)
    except ImportError:
        _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        import sys
        sys.path.insert(0, _here)
        from project import (Project, Journal, Auditor, project_context,
                             file_context, slugify)


def _project_from_args(args, ctx):
    name = args.get("project") or args.get("name")
    if name:
        return Project.open(slugify(name))
    # fall back to ctx.project if rox.py set one
    return getattr(ctx, "project", None)


def project_new(args, ctx):
    name = args.get("name", args.get("project", ""))
    if not name:
        return {"ok": False,
                "output": "project name required. Use the ask_user flow "
                          "to confirm the name with the user first."}
    p = Project.create(slugify(name))
    p.save_meta()
    p.scan()
    if ctx.project is None:
        ctx.project = p
    return {"ok": True, "output":
            f"created project '{p.name}' at {p.source}\n"
            f"ledger: {p.ledger}"}


def project_open(args, ctx):
    p = _project_from_args(args, ctx)
    if p is None:
        return {"ok": False, "output": "no project specified or open"}
    p.scan()
    ctx.project = p
    return {"ok": True, "output": f"opened project '{p.name}'\n"
            f"source: {p.source}\n{project_context(p)}"}


def project_scan(args, ctx):
    p = _project_from_args(args, ctx)
    if p is None:
        return {"ok": False, "output": "no project specified or open"}
    st = p.scan()
    return {"ok": True, "output": f"scanned {p.name}: {st}"}


def project_status(args, ctx):
    p = _project_from_args(args, ctx)
    if p is None:
        return {"ok": False, "output": "no project specified or open"}
    st = p.status()
    lines = [f"project: {st['name']}", f"source: {st['source']}",
             f"files: {st['file_count']}"]
    for c in st["recent_changes"][-15:]:
        lines.append(f"  [{c['status']}] {c['path']}")
    return {"ok": True, "output": "\n".join(lines)}


def project_journal(args, ctx):
    p = _project_from_args(args, ctx)
    if p is None:
        return {"ok": False, "output": "no project specified or open"}
    j = Journal(p)
    rel = args.get("file")
    if rel:
        hist = j.history(rel, limit=int(args.get("limit", 50)))
        if not hist:
            return {"ok": True,
                    "output": f"no journal entries for {rel}"}
        return {"ok": True, "output": "\n".join(
            f"- {e['iso']} {e['action']}: {e['detail'][:150]}"
            for e in hist)}
    return {"ok": True, "output": j.summary(int(args.get("limit", 40)))}


def project_audit(args, ctx):
    p = _project_from_args(args, ctx)
    if p is None:
        return {"ok": False, "output": "no project specified or open"}
    a = Auditor(p)
    r = a.audit(args.get("file"))
    if not r["issues"]:
        return {"ok": True, "output": f"audit of {p.name}: clean "
                f"({r['modules']} modules, {r['files']} files)"}
    lines = [f"audit of {p.name}: {len(r['issues'])} issues"]
    for i in r["issues"][:40]:
        lines.append(f"  [{i['type']}] {i['file']}: {i['detail'][:120]}")
    return {"ok": True, "output": "\n".join(lines)}


def project_map(args, ctx):
    p = _project_from_args(args, ctx)
    if p is None:
        return {"ok": False, "output": "no project specified or open"}
    return {"ok": True, "output": project_context(p)}


def project_related(args, ctx):
    p = _project_from_args(args, ctx)
    if p is None:
        return {"ok": False, "output": "no project specified or open"}
    rel = args.get("file", "")
    rels = p.related(rel)
    if not rels:
        return {"ok": True, "output": f"no related files for {rel}"}
    return {"ok": True, "output": f"related to {rel}:\n" +
            "\n".join(f"- {r}" for r in rels)}


if __name__ == "__main__":
    from types import SimpleNamespace
    ctx = SimpleNamespace(workspace="~/.rox/work", project=None)
    print(project_new({"name": "smoke-test"}, ctx)["output"])
    print(project_audit({}, ctx)["output"][:120])
    print(project_journal({}, ctx)["output"][:120])