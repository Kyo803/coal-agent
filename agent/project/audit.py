"""Project audit: check a multi-file project for consistency problems so
Coal can fix them instead of guessing.

  from project.audit import Auditor
  a = Auditor(project)
  report = a.audit()          # dict of issue lists
"""
from __future__ import annotations

import os
import re


class Auditor:
    def __init__(self, project):
        self.project = project

    def audit(self, rel=None):
        """Run all checks. Returns {issues: [...], counts: {...}}."""
        arch = self.project.architecture()
        issues = []

        # 1. broken / dangling imports
        for m in arch["modules"]:
            if rel and m["path"] != rel:
                continue
            base = m["path"].rsplit("/", 1)[0] + "/"
            for imp in m["imports"]:
                # is there a file named imp.py in the project?
                candidates = [p for p in arch["tree"]
                              if p.endswith(".py")
                              and os.path.splitext(os.path.basename(p))[0]
                              == imp]
                stdlib = {"os", "sys", "json", "re", "math", "random",
                          "time", "datetime", "collections", "itertools",
                          "functools", "pathlib", "typing", "subprocess",
                          "urllib", "socket", "threading", "asyncio",
                          "sqlite3", "hashlib", "base64", "csv", "io",
                          "glob", "shutil", "tempfile", "uuid", "logging",
                          "argparse", "ctypes", "statistics", "struct",
                          "concurrent", "dataclasses", "enum", "abc",
                          "decimal", "fractions", "queue", "heapq",
                          "bisect", "copy", "pprint", "textwrap", "string",
                          "unicodedata", "secrets", "hmac", "getpass",
                          "platform", "signal", "errno", "traceback",
                          "warnings", "contextlib", "inspect", "operator",
                          "types", "weakref", "array", "pickle", "zlib",
                          "gzip", "tarfile", "zipfile", "http", "email",
                          "html", "xml", "configparser", "tomllib",
                          "unittest", "doctest", "venv", "atexit"}
                # common third-party packages that resolve via pip
                third_party = {"requests", "numpy", "pandas", "flask",
                               "django", "fastapi", "pydantic", "bs4",
                               "beautifulsoup4", "selenium", "playwright",
                               "pytest", "scrapy", "aiohttp", "httpx",
                               "torch", "tensorflow", "sklearn", "scipy",
                               "matplotlib", "pyyaml", "dotenv", "click",
                               "rich", "tqdm", "lxml", "openai", "boto3",
                               "redis", "celery", "sqlalchemy", "pymongo",
                               "psycopg2", "duckdb"}
                if not candidates and imp not in stdlib \
                        and imp not in third_party \
                        and not imp.startswith("."):
                    issues.append({"type": "missing_import",
                                   "file": m["path"],
                                   "detail": f"imports '{imp}' but no "
                                             f"matching module found"})

        # 2. duplicate symbols across files
        seen = {}
        for m in arch["modules"]:
            for s in m["symbols"]:
                if s["kind"] != "class":
                    continue
                seen.setdefault(s["name"], []).append(m["path"])
        for name, paths in seen.items():
            if len(paths) > 1:
                issues.append({"type": "duplicate_class",
                               "file": ", ".join(paths),
                               "detail": f"class '{name}' defined in "
                                         f"{len(paths)} files"})

        # 3. TODO / FIXME / HACK markers
        for m in arch["modules"]:
            try:
                with open(os.path.join(self.project.source, m["path"]),
                          encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if re.search(r"\b(TODO|FIXME|HACK|XXX)\b", line):
                            issues.append({"type": "marker",
                                           "file": m["path"],
                                           "detail": f"line {i}: "
                                                     f"{line.strip()[:80]}"})
            except Exception:
                continue

        # 4. orphaned files (no imports reference them, not entry points)
        if not rel:
            imported = set()
            for m in arch["modules"]:
                imported.update(m["imports"])
            for p in arch["tree"]:
                base = os.path.splitext(os.path.basename(p))[0]
                if p.endswith(".py") and base not in imported and \
                        base not in ("main", "__init__", "setup",
                                     "manage", "run"):
                    issues.append({"type": "orphan",
                                   "file": p,
                                   "detail": "not imported by anything"})

        counts = {}
        for i in issues:
            counts[i["type"]] = counts.get(i["type"], 0) + 1
        return {"issues": issues, "counts": counts,
                "modules": len(arch["modules"]),
                "files": len(arch["tree"])}


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
    open(os.path.join(p.source, "main.py"), "w").write(
        "import missing_module\nimport helper\n\ndef run():\n    return 1\n")
    open(os.path.join(p.source, "helper.py"), "w").write(
        "class Widget:\n    pass\n# TODO: finish\n")
    open(os.path.join(p.source, "widget.py"), "w").write(
        "class Widget:\n    pass\n")
    a = Auditor(p)
    r = a.audit()
    print("counts:", r["counts"])
    for i in r["issues"]:
        print(f"  {i['type']:16s} {i['file']}: {i['detail'][:60]}")
    print("[audit] OK")