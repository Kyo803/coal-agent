"""Project model: tracks a multi-file project so Coal knows exactly what
lives in every file, what changed, and how files relate.

Source folder  -> Desktop\\Coal Projects\\<name>\\        (real Desktop path)
Ledger         -> ~/.coal/projects/<name>\\               (clean, not in repo)

  from project.project import Project
  p = Project.create("robot-arm")
  p.scan()                       # hash-track every file
  p.status()                     # {files, new, changed, deleted}
  p.architecture()               # tree + symbols + imports
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             "dist", "build", ".idea", ".vscode", ".coal"}
TEXT_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp",
             ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift",
             ".kt", ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
             ".ini", ".cfg", ".html", ".css", ".scss", ".xml", ".sh",
             ".bat", ".ps1", ".sql", ".env"}


def desktop_root():
    """Real Desktop path (handles OneDrive redirection)."""
    import ctypes
    buf = ctypes.create_unicode_buffer(512)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x0000, None, 0, buf)
    return buf.value or os.path.join(os.path.expanduser("~"), "Desktop")


def slugify(name):
    """'My Robot Arm!' -> 'my-robot-arm'"""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "project"


def safe_name(name):
    """Validate a project name -> safe folder name or raise."""
    if not name or name.strip() in (".", ".."):
        raise ValueError("invalid project name")
    if any(c in name for c in '<>:"/\\|?*'):
        raise ValueError(f"name has illegal characters: {name}")
    return name.strip()


class Project:
    def __init__(self, name, source_root=None, ledger_root=None):
        self.name = safe_name(name)
        self.source = os.path.join(source_root or os.path.join(
            desktop_root(), "Coal Projects"), self.name)
        self.ledger = os.path.join(ledger_root or os.path.expanduser(
            "~/.coal/projects"), self.name)
        os.makedirs(self.source, exist_ok=True)
        os.makedirs(self.ledger, exist_ok=True)
        self.db_path = os.path.join(self.ledger, "project.db")
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
              path TEXT PRIMARY KEY,
              hash TEXT, size INTEGER, mtime REAL,
              status TEXT, first_seen REAL, last_seen REAL
            );
        """)
        self._conn.commit()
        self.arch_path = os.path.join(self.ledger, "architecture.json")

    # ---- lifecycle ----
    @classmethod
    def create(cls, name, source_root=None, ledger_root=None):
        return cls(name, source_root, ledger_root)

    @classmethod
    def open(cls, name, **kw):
        return cls(name, **kw)

    @classmethod
    def list_projects(cls, ledger_root=None):
        root = ledger_root or os.path.expanduser("~/.coal/projects")
        if not os.path.isdir(root):
            return []
        return [d for d in sorted(os.listdir(root))
                if os.path.isdir(os.path.join(root, d))]

    @classmethod
    def find_by_path(cls, path):
        """Find the Coal project that owns a given file path."""
        path = os.path.abspath(path)
        root = os.path.expanduser("~/.coal/projects")
        if not os.path.isdir(root):
            return None
        for d in os.listdir(root):
            ledger = os.path.join(root, d)
            meta = os.path.join(ledger, "meta.json")
            if os.path.exists(meta):
                try:
                    m = json.load(open(meta, encoding="utf-8"))
                    src = m.get("source", "")
                    if src and os.path.abspath(src) and (
                            path == os.path.abspath(src) or
                            path.startswith(os.path.abspath(src) + os.sep)):
                        return Project(d)
                except Exception:
                    continue
        return None

    # ---- scan / ledger ----
    def _hash(self, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()[:16]

    def scan(self):
        """Walk source tree, hash each file, update ledger. Returns stats."""
        now = time.time()
        seen = set()
        new = changed = unchanged = 0
        for dirpath, dirnames, filenames in os.walk(self.source):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                rel = os.path.relpath(fp, self.source).replace("\\", "/")
                seen.add(rel)
                try:
                    st = os.stat(fp)
                    fhash = self._hash(fp)
                except OSError:
                    continue
                row = self._conn.execute(
                    "SELECT hash FROM files WHERE path=?", (rel,)).fetchone()
                if row is None:
                    new += 1
                    status = "new"
                elif row[0] != fhash:
                    changed += 1
                    status = "changed"
                else:
                    unchanged += 1
                    status = "unchanged"
                self._conn.execute(
                    "INSERT INTO files(path,hash,size,mtime,status,"
                    "first_seen,last_seen) VALUES(?,?,?,?,?,"
                    "COALESCE((SELECT first_seen FROM files WHERE path=?),"
                    "?),?) "
                    "ON CONFLICT(path) DO UPDATE SET hash=excluded.hash,"
                    "size=excluded.size,mtime=excluded.mtime,"
                    "status=excluded.status,last_seen=excluded.last_seen",
                    (rel, fhash, st.st_size, st.st_mtime, status, rel, now,
                     now))
        # mark missing (deleted)
        existing = [r[0] for r in
                    self._conn.execute("SELECT path FROM files").fetchall()]
        deleted = 0
        for rel in existing:
            if rel not in seen:
                self._conn.execute(
                    "UPDATE files SET status='deleted', last_seen=? "
                    "WHERE path=?", (now, rel))
                deleted += 1
        self._conn.commit()
        return {"files": len(seen), "new": new, "changed": changed,
                "unchanged": unchanged, "deleted": deleted}

    def status(self):
        rows = self._conn.execute(
            "SELECT path,status,size,mtime FROM files "
            "ORDER BY last_seen DESC").fetchall()
        files = [{"path": r[0], "status": r[1], "size": r[2],
                  "mtime": r[3]} for r in rows]
        changed = [f for f in files if f["status"] in ("new", "changed",
                                                       "deleted")]
        return {"name": self.name, "source": self.source,
                "ledger": self.ledger, "file_count": len(files),
                "recent_changes": changed[-20:]}

    def file_hash(self, rel):
        r = self._conn.execute("SELECT hash FROM files WHERE path=?",
                               (rel,)).fetchone()
        return r[0] if r else None

    def save_meta(self):
        json.dump({"name": self.name, "source": self.source,
                   "ledger": self.ledger, "created": time.time()},
                  open(os.path.join(self.ledger, "meta.json"), "w"),
                  indent=1)

    # ---- architecture ----
    def _symbols(self, path):
        out = []
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    m = re.match(r"\s*(?:def|class|async def)\s+([\w]+)",
                                 line)
                    if m:
                        out.append({"line": i, "name": m.group(1),
                                    "kind": "class" if
                                    line.strip().startswith("class")
                                    else "function"})
        except Exception:
            pass
        return out

    def _imports(self, path):
        deps = set()
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = re.match(r"\s*(?:from\s+([\w.]+)\s+import|"
                                 r"import\s+([\w.]+))", line)
                    if m:
                        mod = (m.group(1) or m.group(2)).split(".")[0]
                        if mod != "__future__":
                            deps.add(mod)
        except Exception:
            pass
        return sorted(deps)

    def architecture(self, refresh=False):
        if not refresh and os.path.exists(self.arch_path):
            try:
                arch = json.load(open(self.arch_path, encoding="utf-8"))
                # stale check: if cached tree misses a file that now
                # exists on disk, refresh automatically.
                cached = set(arch.get("tree", []))
                live = set()
                for dirpath, dirnames, filenames in os.walk(self.source):
                    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                    for fn in filenames:
                        rel = os.path.relpath(os.path.join(dirpath, fn),
                                              self.source)
                        live.add(rel.replace("\\", "/"))
                if cached == live:
                    return arch
            except Exception:
                pass
        self.scan()
        tree = []
        modules = []
        for dirpath, dirnames, filenames in os.walk(self.source):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                rel = os.path.relpath(fp, self.source).replace("\\", "/")
                ext = os.path.splitext(fn)[1].lower()
                tree.append(rel)
                if ext in TEXT_EXTS:
                    modules.append({
                        "path": rel,
                        "symbols": self._symbols(fp),
                        "imports": self._imports(fp),
                    })
        arch = {"name": self.name, "source": self.source,
                "tree": tree, "modules": modules}
        json.dump(arch, open(self.arch_path, "w", encoding="utf-8"),
                  indent=1)
        return arch

    def related(self, rel, depth=1):
        """Files related to `rel`: its imports + files that import it."""
        arch = self.architecture()
        rel = rel.replace("\\", "/")
        mod = next((m for m in arch["modules"] if m["path"] == rel), None)
        if not mod:
            return []
        related = set()
        base = os.path.splitext(rel)[0]
        for imp in mod["imports"]:
            for m in arch["modules"]:
                if imp in m["path"] and m["path"] != rel:
                    related.add(m["path"])
        # reverse: who imports this module?
        stub = base.replace("/", ".").split(".")[-1]
        for m in arch["modules"]:
            if rel in m["imports"] or stub in m["imports"]:
                related.add(m["path"])
        return sorted(related)[:20]

    def close(self):
        try:
            self.save_meta()
            self._conn.commit()
            self._conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    import tempfile
    tmp = tempfile.mkdtemp()
    p = Project.create("demo", source_root=tmp,
                       ledger_root=os.path.join(tmp, "ledger"))
    os.makedirs(os.path.join(p.source, "src"))
    open(os.path.join(p.source, "src", "main.py"), "w").write(
        "import helper\n\ndef run():\n    return helper.add(1,2)\n")
    open(os.path.join(p.source, "src", "helper.py"), "w").write(
        "def add(a,b):\n    return a+b\n")
    print("scan:", p.scan())
    arch = p.architecture(refresh=True)
    print("tree:", arch["tree"])
    print("related(main.py):", p.related("src/main.py"))
    p.close()
    print("[project] OK")