"""Core memory: the user profile. Small, always in the prompt, both
auto-updated (by consolidation) and hand-editable by the user."""
import json
import os
import time


class Profile:
    DEFAULTS = {
        "name": None,
        "style": "neutral",       # communication preference
        "entities": [],
        "likes": [],
        "dislikes": [],
        "project": [],
        "notes": [],
    }

    def __init__(self, path):
        self.path = path
        self.persist = path is not None and path != ":memory:"
        if self.persist:
            os.makedirs(os.path.dirname(os.path.abspath(path)),
                        exist_ok=True)
        self.data = dict(self.DEFAULTS)
        if self.persist and os.path.exists(path):
            try:
                self.data.update(json.load(open(path, encoding="utf-8")))
            except Exception:
                pass

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def set_many(self, key, values):
        cur = self.data.get(key) or []
        if not isinstance(cur, list):
            cur = [cur]
        for v in values:
            if v not in cur:
                cur.append(v)
        self.data[key] = cur[:10]
        self.save()

    def get(self, key, default=None):
        return self.data.get(key, default)

    def save(self):
        if not self.persist:
            return
        json.dump(self.data, open(self.path, "w", encoding="utf-8"),
                  indent=1)

    def render(self, max_chars=600):
        """Compact text form for the prompt."""
        lines = []
        if self.data.get("name"):
            lines.append(f"User's name: {self.data['name']}")
        if self.data.get("style") and self.data["style"] != "neutral":
            lines.append(f"Preferred style: {self.data['style']}")
        for key in ("project", "likes", "dislikes", "entities"):
            vals = self.data.get(key) or []
            if vals:
                lines.append(f"{key.capitalize()}: {', '.join(map(str, vals[:6]))}")
        if self.data.get("notes"):
            lines.append("Notes: " + "; ".join(map(str, self.data["notes"][:4])))
        txt = "\n".join(lines)
        return txt[:max_chars]

    def __repr__(self):
        return f"Profile({json.dumps(self.data)[:80]})"


if __name__ == "__main__":
    import tempfile
    p = Profile(os.path.join(tempfile.mkdtemp(), "profile.json"))
    p.set("name", "WERU")
    p.set_many("project", ["industrial robot arm", "ROX N"])
    p.set_many("likes", ["embedded systems"])
    print("[profile]", repr(p.render()))
