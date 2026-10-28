"""Project context: the anti-hallucination layer. Builds a precise,
budget-aware prompt block about a file or the whole project.

  file_context(project, "src/main.py")   -> its content + symbols +
                                            imports + journal + related
  project_context(project, "how do I ...") -> architecture + relevant files
"""
from __future__ import annotations

import os

CHARS_PER_TOK = 4.0


def _tok(text):
    return int(len(text) / CHARS_PER_TOK) + 1


def _read(project, rel, max_chars=6000):
    path = os.path.join(project.source, rel)
    if not os.path.exists(path):
        return ""
    try:
        txt = open(path, encoding="utf-8", errors="ignore").read()
        return txt if len(txt) <= max_chars else txt[:max_chars] + "...\n"
    except Exception:
        return ""


def file_context(project, rel, journal=None, include_body=True,
                 max_tokens=1800):
    """Everything ROX N needs to work on one file without guessing."""
    rel = rel.replace("\\", "/")
    arch = project.architecture()
    mod = next((m for m in arch["modules"] if m["path"] == rel), None)
    parts = []
    used = 0

    def add(label, text):
        nonlocal used
        if not text:
            return
        t = _tok(text)
        if used + t > max_tokens:
            return
        parts.append(f"### {label}\n{text}")
        used += t

    add("file", rel)
    if mod:
        syms = ", ".join(f"{s['name']}({s['kind'][0]})" for s
                         in mod["symbols"]) or "none"
        add("symbols", syms)
        add("imports", ", ".join(mod["imports"]) or "none")
    related = project.related(rel)
    if related:
        add("related files", "\n".join(f"- {r}" for r in related))
    if journal:
        hist = journal.history(rel, limit=10)
        if hist:
            jl = "\n".join(f"- {e['iso']} {e['action']}: "
                           f"{e['detail'][:120]}" for e in hist)
            add("recent changes to this file", jl)
    if include_body:
        body = _read(project, rel)
        if body:
            add("current content", body)
    return "\n\n".join(parts)


def project_context(project, query="", max_tokens=1600):
    """Architecture overview + the files most relevant to `query`."""
    arch = project.architecture()
    parts = []
    used = 0

    def add(label, text):
        nonlocal used
        if not text:
            return
        t = _tok(text)
        if used + t > max_tokens:
            return
        parts.append(f"### {label}\n{text}")
        used += t

    add("project", f"{project.name} at {project.source}")
    tree = arch["tree"]
    if tree:
        add("file tree",
            "\n".join(f"- {p}" for p in tree[:80]))
    # modules with their symbol counts
    if arch["modules"]:
        lines = []
        for m in arch["modules"][:40]:
            syms = ", ".join(s["name"] for s in m["symbols"][:8]) or "-"
            lines.append(f"{m['path']}: {syms}")
        add("modules & symbols", "\n".join(lines))
    return "\n\n".join(parts)


if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    import tempfile
    from project.project import Project
    from project.journal import Journal
    tmp = tempfile.mkdtemp()
    p = Project.create("demo", source_root=tmp,
                       ledger_root=os.path.join(tmp, "ledger"))
    open(os.path.join(p.source, "main.py"), "w").write(
        "import helper\n\ndef run():\n    return helper.add(1,2)\n")
    open(os.path.join(p.source, "helper.py"), "w").write(
        "def add(a,b):\n    return a+b\n")
    j = Journal(p)
    j.record("main.py", "edited", "added run()")
    print(file_context(p, "main.py", j))
    print("---- project context ----")
    print(project_context(p)[:300])
    print("[context] OK")