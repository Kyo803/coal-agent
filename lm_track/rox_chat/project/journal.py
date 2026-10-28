"""Fine-grained change journal: every write/edit/delete/rename in a
project is recorded so ROX N can recall exactly what happened, when.

Append-only JSONL per project ledger. Never rewrites history.

  from project.journal import Journal
  j = Journal(project)
  j.record("src/main.py", "edited", "added run()")
  j.history("src/main.py")   # all entries for one file
  j.today()                  # all of today's changes
"""
from __future__ import annotations

import json
import os
import time


class Journal:
    def __init__(self, project):
        self.project = project
        self.path = os.path.join(project.ledger, "journal.jsonl")
        os.makedirs(project.ledger, exist_ok=True)

    def record(self, rel, action, detail="", meta=None):
        """Append one entry. rel is project-relative path (or 'root' for
        project-level events like 'created')."""
        entry = {
            "time": time.time(),
            "iso": time.strftime("%Y-%m-%d %H:%M:%S"),
            "file": str(rel).replace("\\", "/"),
            "action": action,          # created|edited|deleted|renamed|added
            "detail": str(detail)[:2000],
            "meta": meta or {},
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def _read(self):
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        continue
        return out

    def history(self, rel=None, limit=200):
        entries = self._read()
        if rel:
            rel = rel.replace("\\", "/")
            entries = [e for e in entries if e["file"] == rel]
        return entries[-limit:]

    def latest(self, rel):
        h = self.history(rel, limit=1)
        return h[0] if h else None

    def since(self, cutoff_iso, rel=None):
        entries = self.history(rel, limit=100000)
        return [e for e in entries if e["iso"] >= cutoff_iso]

    def today(self):
        day = time.strftime("%Y-%m-%d")
        return self.history(limit=100000) and \
            [e for e in self._read() if e["iso"].startswith(day)]

    def by_file(self):
        """grouped {file: [entries]} for the whole project."""
        g = {}
        for e in self._read():
            g.setdefault(e["file"], []).append(e)
        return g

    def summary(self, limit=40):
        """Human-readable digest of the latest activity."""
        entries = self._read()[-limit:]
        if not entries:
            return "(no changes recorded yet)"
        lines = []
        for e in entries:
            lines.append(f"{e['iso']}  {e['action']:9s} {e['file']} "
                         f"{('- ' + e['detail']) if e['detail'] else ''}")
        return "\n".join(lines)

    def count(self):
        return len(self._read())


if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    import tempfile
    from project.project import Project
    tmp = tempfile.mkdtemp()
    p = Project.create("demo", source_root=tmp,
                       ledger_root=os.path.join(tmp, "ledger"))
    j = Journal(p)
    j.record("src/main.py", "created", "new entry point")
    j.record("src/main.py", "edited", "added run()")
    j.record("src/helper.py", "created", "utility module")
    j.record("src/main.py", "edited", "import helper")
    print("summary:\n" + j.summary())
    print("history(main.py):", len(j.history("src/main.py")), "entries")
    print("[journal] OK")