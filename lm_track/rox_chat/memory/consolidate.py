"""Memory consolidation: extract durable facts + summarize sessions.

Runs at session end / every N turns. Deterministic patterns (no model
needed) + entity extraction. Writes to facts/entities/summaries and
updates the profile. This is what makes "remembers everything" work.
"""
import re
import time

# (regex, predicate, group) -> fact from user self-disclosure
PATTERNS = [
    (re.compile(r"\bmy name is ([A-Za-z][\w'-]{1,30})", re.I), "name", 1),
    (re.compile(r"\bi(?:'m| am) (?:a|an) ([\w][\w\s-]{1,40})", re.I),
     "is_a", 1),
    (re.compile(r"\bi work (?:at|for|on) ([\w][\w\s&.,-]{2,60})", re.I),
     "works_on", 1),
    (re.compile(r"\bi(?:'m| am) (?:building|making|working on) "
                r"([\w][\w\s&.,-]{2,60})", re.I), "builds", 1),
    (re.compile(r"\bi (?:like|love|enjoy) ([\w][\w\s&.,-]{2,40})", re.I),
     "likes", 1),
    (re.compile(r"\bi (?:hate|dislike) ([\w][\w\s&.,-]{2,40})", re.I),
     "dislikes", 1),
    (re.compile(r"\bmy (?:dog|cat|pet)(?:'s name)? is (?:named )?"
                r"([\w-]{1,30})", re.I), "pet_name", 1),
    (re.compile(r"\bi live in ([\w][\w\s,.-]{2,40})", re.I), "lives_in", 1),
    (re.compile(r"\bi(?:'m| am) (\d{1,3}) years old", re.I), "age", 1),
    (re.compile(r"\bmy (?:project|company|startup) is (?:called )?"
                r"([\w][\w\s&.,-]{2,60})", re.I), "project", 1),
    (re.compile(r"\bi use ([\w][\w\s+.#-]{2,40})", re.I), "uses", 1),
]

# trailing fragments that signal the phrase ended
_TAIL = re.compile(r"\s+(?:and|but|so|because|which|that)\s+.*$", re.I)

ENTITY_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b")
ENTITY_STOP = {"The", "This", "That", "And", "But", "For", "With", "You",
               "Your", "What", "When", "Where", "How", "Why", "Yes", "No",
               "I", "It", "Is", "Are", "My", "We", "They", "He", "She"}


class Consolidator:
    def __init__(self, store, embedder, index, every_n=8):
        self.store = store
        self.embedder = embedder
        self.index = index
        self.every_n = every_n

    def extract_facts(self, sid, limit=200):
        msgs = self.store.recent_messages(sid=sid, limit=limit)
        n_new = 0
        for m in msgs:
            if m["role"] != "user":
                continue
            text = m["text"]
            for rx, pred, grp in PATTERNS:
                for mt in rx.finditer(text):
                    val = mt.group(grp).strip().rstrip(".,!?")
                    val = _TAIL.sub("", val).strip()  # cut trailing clause
                    val = re.sub(r"^(?:named|a|an|the)\s+", "", val,
                                 flags=re.I).strip()
                    if 1 <= len(val) <= 60:
                        self.store.add_fact("user", pred, val, 0.8,
                                            source_msg=m["id"])
                        n_new += 1
            for em in ENTITY_RE.finditer(text):
                name = em.group(1)
                if name not in ENTITY_STOP and len(name) > 2:
                    self.store.upsert_entity(name, "entity")
        return n_new

    def summarize(self, sid, max_sentences=6):
        msgs = self.store.recent_messages(sid=sid, limit=400)
        if not msgs:
            return None
        # score sentences by length + keyword density
        scored = []
        for m in msgs:
            for s in re.split(r"(?<=[.!?])\s+", m["text"]):
                s = s.strip()
                if len(s) < 20:
                    continue
                scored.append((len(s) + 5 * (s.count(" ") > 4), s))
        scored.sort(key=lambda x: -x[0])
        picked = [s for _sc, s in scored[:max_sentences]]
        # keep chronological order
        order = {s: i for i, (_sc, s) in enumerate(scored)}
        picked.sort(key=lambda s: order.get(s, 0))
        summary = " ".join(picked)[:1500]
        self.store.add_summary(sid, 1, summary)
        return summary

    def update_profile(self, profile):
        facts = self.store.all_facts(limit=200)
        agg = {}
        for f in facts:
            key = f["predicate"]
            agg.setdefault(key, [])
            if f["object"] not in agg[key]:
                agg[key].append(f["object"])
        for key, vals in agg.items():
            profile.set_many(key, vals[:5])
        ents = self.store.top_entities(limit=15)
        profile.set_many("entities", [e["name"] for e in ents])
        return agg

    def run(self, sid, profile=None):
        n = self.extract_facts(sid)
        summ = self.summarize(sid)
        if profile is not None:
            self.update_profile(profile)
        self.store.end_session(sid, summ)
        self.index.flush()
        return {"facts_added": n, "summary": (summ or "")[:120]}

    # ---- model-based extraction (uses the local 35B when available) ----
    def extract_facts_model(self, sid, limit=20, max_facts=12):
        """Ask the local model to extract durable facts as JSON. Falls
        back to the regex path on any failure."""
        try:
            from streaming import stream_chat
        except Exception:
            return self.extract_facts(sid, limit)
        msgs = self.store.recent_messages(sid=sid, limit=limit)
        if not msgs:
            return 0
        convo = "\n".join(f"{m['role']}: {m['text'][:400]}" for m in msgs)
        prompt = (
            "Extract durable facts about the USER from this conversation. "
            "Return ONLY a JSON array of objects with keys "
            "subject, predicate, object. Examples: "
            '{"subject":"user","predicate":"pet_name","object":"Biscuit"}. '
            "Only include facts worth remembering across sessions "
            "(names, projects, preferences, hardware, goals). "
            f"If none, return [].\n\nConversation:\n{convo}\n\nJSON:")
        try:
            text, _, _ = stream_chat(
                [{"role": "user", "content": prompt}], thinking=False,
                max_tokens=400)
            import re as _re
            m = _re.search(r"\[.*\]", text, _re.S)
            if not m:
                return self.extract_facts(sid, limit)
            data = json.loads(m.group(0))
            n = 0
            for f in data[:max_facts]:
                sub = str(f.get("subject", "user"))[:40]
                pred = str(f.get("predicate", ""))[:40]
                obj = str(f.get("object", ""))[:120]
                if pred and obj:
                    self.store.add_fact(sub, pred, obj, 0.9)
                    n += 1
            return n
        except Exception:
            return self.extract_facts(sid, limit)
