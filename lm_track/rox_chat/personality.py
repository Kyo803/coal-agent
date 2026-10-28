"""ROX N personality: adaptable, learns from how you talk.

Base traits come from config. As you chat, the personality observes your
style (message length, formality, humour, directness) and drifts toward
it — so Rox gradually talks the way you do. Persists to
<memory_root>/personality.json.

Traits in [0,1]: warmth, directness, humor, formality, verbosity.
"""
import json
import os
import re
import time

TRAITS = ["warmth", "directness", "humor", "formality", "verbosity"]

FORMAL = ["please", "kindly", "regards", "thank you", "would you",
          "could you", "sir", "madam"]
CASUAL = ["hey", "yo", "lol", "haha", "gonna", "wanna", "dude", "bro",
          "nah", "yeah", "ok", "okay"]
HUMOR = ["lol", "haha", "joke", "funny", ":)", "😄", "😂", "lmao"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


class Personality:
    def __init__(self, root=None, base=None, adapt=True):
        from rox_config import cfg
        self.root = root or cfg.memory_root
        self.path = os.path.join(self.root, "personality.json")
        self.adapt = adapt
        self.name = cfg.personality.get("name", "Rox")
        self.base = dict(base or cfg.personality.get("base_traits", {}))
        for t in TRAITS:
            self.base.setdefault(t, 0.5)
        self.traits = dict(self.base)
        self.samples = 0
        self.style_notes = []       # short observations about the user
        self.load()

    # ---- persistence ----
    def load(self):
        if os.path.exists(self.path):
            try:
                d = json.load(open(self.path, encoding="utf-8"))
                self.traits.update(d.get("traits", {}))
                self.samples = d.get("samples", 0)
                self.style_notes = d.get("style_notes", [])
                self.name = d.get("name", self.name)
            except Exception:
                pass

    def save(self):
        os.makedirs(self.root, exist_ok=True)
        json.dump({"name": self.name, "traits": self.traits,
                   "base": self.base, "samples": self.samples,
                   "style_notes": self.style_notes[-20:],
                   "updated": time.time()},
                  open(self.path, "w", encoding="utf-8"), indent=1)

    # ---- observation ----
    @staticmethod
    def _observe(text):
        t = (text or "").lower()
        words = re.findall(r"[a-z']+", t)
        n = max(1, len(words))
        return {
            "verbosity": min(1.0, len(words) / 60.0),
            "formality": min(1.0,
                             sum(1 for w in FORMAL if w in t) / 3.0),
            "humor": min(1.0, sum(1 for w in HUMOR if w in t) / 2.0),
            "directness": min(1.0, 1.0 - sum(1 for w in CASUAL if w in t)
                              / max(3, n // 6)),
            "warmth": min(1.0, (sum(1 for w in CASUAL if w in t) + 1) / 4.0),
            "emoji": len(EMOJI.findall(text or "")),
        }

    def observe(self, user_text):
        """Drift traits toward the user's observed style (EMA)."""
        if not self.adapt:
            return
        o = self._observe(user_text)
        a = 0.15  # adaptation rate
        for t in TRAITS:
            self.traits[t] = round(
                (1 - a) * self.traits[t] + a * o.get(t, self.traits[t]), 4)
        self.samples += 1
        if o["emoji"] > 0:
            note = "user uses emoji"
            if note not in self.style_notes:
                self.style_notes.append(note)
        if self.samples % 5 == 0:
            self.save()

    def absorb_facts(self, facts):
        """Turn durable facts into style notes (e.g. 'likes concise')."""
        for f in facts:
            pred = f.get("predicate", "")
            obj = str(f.get("object", ""))
            if pred in ("style", "preference") or "concise" in obj.lower():
                note = f"{pred}: {obj}"
                if note not in self.style_notes:
                    self.style_notes.append(note)
        self.save()

    # ---- prompt ----
    def describe(self):
        t = self.traits
        bits = []
        bits.append("very warm" if t["warmth"] > 0.7 else
                    "reserved" if t["warmth"] < 0.35 else "friendly")
        bits.append("very direct" if t["directness"] > 0.7 else
                    "gentle" if t["directness"] < 0.4 else "clear")
        if t["humor"] > 0.55:
            bits.append("playful")
        if t["formality"] > 0.6:
            bits.append("formal")
        elif t["formality"] < 0.35:
            bits.append("casual")
        bits.append("detailed" if t["verbosity"] > 0.6 else
                    "brief" if t["verbosity"] < 0.4 else "moderate")
        return ", ".join(bits)

    def system_prompt(self, extra_context=None):
        p = [f"You are {self.name}, a local assistant built in the ROX N "
             f"project. You run entirely on the user's machine.",
             f"Your style is {self.describe()}.",
             "You are capable, not limited to chatting: you control a full "
             "root Linux sandbox (Ubuntu) with the internet and 400+ tools. "
             "You can install anything, clone repos, run any command, build "
             "and test real multi-file projects, learn on your own, and "
             "improve yourself. Plan and act; never claim you cannot do "
             "something your tools can do. When a task needs Linux, use the "
             "sandbox tools.",
             "Use the memory tools whenever the user refers to past "
             "conversations, their projects, preferences or personal "
             "facts. Never invent facts; if unsure, say so."]
        if self.style_notes:
            p.append("Things you've learned about the user: " +
                     "; ".join(self.style_notes[-6:]))
        if extra_context:
            p.append("Known context:\n" + extra_context)
        return "\n".join(p)


if __name__ == "__main__":
    import tempfile
    p = Personality(root=tempfile.mkdtemp(), adapt=True)
    for msg in ["hey dude lol, what's up", "Please kindly summarize this "
                "document for me, thank you", "yo that's funny haha"]:
        p.observe(msg)
    print("traits:", json.dumps(p.traits, indent=1))
    print("desc:", p.describe())
    print("--- prompt ---")
    print(p.system_prompt()[:300])
