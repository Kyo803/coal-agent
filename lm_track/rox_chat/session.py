"""ROX N sessions: save, resume, list, export conversations.

Sessions are JSON files under <memory_root>/sessions/. Each holds the
turn list + metadata so you can resume exactly where you left off, or
export a chat to markdown.

  from session import Session
  s = Session.resume("work") or Session("work")
  s.add("user", "hi"); s.add("assistant", "hello")
  s.save()
  s.export_markdown("chat.md")
"""
import json
import os
import time

from rox_config import cfg


class Session:
    def __init__(self, name=None, root=None):
        self.root = root or os.path.join(cfg.memory_root, "sessions")
        os.makedirs(self.root, exist_ok=True)
        self.name = name or time.strftime("session-%Y%m%d-%H%M%S")
        self.created = time.time()
        self.updated = self.created
        self.turns = []           # [{"role", "text", "t": ts, "meta"}]
        self.summary = ""

    # ---- lifecycle ----
    @property
    def path(self):
        safe = "".join(c for c in self.name if c.isalnum() or c in "-_ ")
        return os.path.join(self.root, safe.strip() + ".json")

    def add(self, role, text, meta=None):
        self.turns.append({"role": role, "text": text,
                           "t": time.time(), "meta": meta or {}})
        self.updated = time.time()
        return self

    def save(self):
        json.dump({"name": self.name, "created": self.created,
                   "updated": self.updated, "summary": self.summary,
                   "turns": self.turns},
                  open(self.path, "w", encoding="utf-8"), indent=1)
        return self.path

    @classmethod
    def resume(cls, name, root=None):
        root = root or os.path.join(cfg.memory_root, "sessions")
        safe = "".join(c for c in name if c.isalnum() or c in "-_ ")
        p = os.path.join(root, safe.strip() + ".json")
        if not os.path.exists(p):
            return None
        d = json.load(open(p, encoding="utf-8"))
        s = cls(d["name"], root)
        s.created = d.get("created", s.created)
        s.updated = d.get("updated", s.updated)
        s.summary = d.get("summary", "")
        s.turns = d.get("turns", [])
        return s

    @classmethod
    def latest(cls, root=None):
        root = root or os.path.join(cfg.memory_root, "sessions")
        if not os.path.isdir(root):
            return None
        files = [os.path.join(root, f) for f in os.listdir(root)
                 if f.endswith(".json")]
        if not files:
            return None
        newest = max(files, key=os.path.getmtime)
        return cls.resume(os.path.splitext(os.path.basename(newest))[0],
                          root)

    @staticmethod
    def list_sessions(root=None):
        root = root or os.path.join(cfg.memory_root, "sessions")
        out = []
        if os.path.isdir(root):
            for f in sorted(os.listdir(root)):
                if not f.endswith(".json"):
                    continue
                p = os.path.join(root, f)
                try:
                    d = json.load(open(p, encoding="utf-8"))
                    out.append({"name": d["name"],
                                "turns": len(d.get("turns", [])),
                                "updated": d.get("updated", 0)})
                except Exception:
                    continue
        return sorted(out, key=lambda x: -x["updated"])

    # ---- views ----
    def messages(self, limit=None):
        """Chat messages for the model (role/content)."""
        turns = self.turns[-limit:] if limit else self.turns
        return [{"role": t["role"], "content": t["text"]} for t in turns
                if t["role"] in ("user", "assistant", "system")]

    def export_markdown(self, path=None):
        path = path or os.path.join(self.root, self.name + ".md")
        lines = [f"# ROX N session: {self.name}", "",
                 f"_created {time.strftime('%Y-%m-%d %H:%M', time.localtime(self.created))}_",
                 ""]
        for t in self.turns:
            who = "You" if t["role"] == "user" else "Rox"
            lines.append(f"**{who}:** {t['text']}")
            lines.append("")
        if self.summary:
            lines += ["## Summary", "", self.summary, ""]
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        return path

    def stats(self):
        return {"name": self.name, "turns": len(self.turns),
                "updated": self.updated, "summary": bool(self.summary)}


if __name__ == "__main__":
    import tempfile
    root = os.path.join(tempfile.mkdtemp(), "sessions")
    s = Session("demo", root)
    s.add("user", "Hi, I'm WERU")
    s.add("assistant", "Hello WERU!")
    s.add("user", "I build robot arms")
    s.save()
    r = Session.resume("demo", root)
    print("resumed turns:", len(r.turns))
    print("messages:", r.messages())
    print("list:", Session.list_sessions(root))
    print("export:", r.export_markdown())
