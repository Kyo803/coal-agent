"""Context assembly: build the prompt within a token budget from the
five memory tiers, in priority order.

Order (highest priority first):
  1. core      -> user profile (always)
  2. semantic  -> facts relevant to the query
  3. episodic  -> retrieved past turns
  4. knowledge -> (optional) doc passages
  5. working   -> current session tail (verbatim, most recent)

Budget is in *tokens* (approx 4 chars/token). Tiers are added greedily;
working memory always keeps the last few turns even if over budget.
"""
import re

CHARS_PER_TOK = 4.0


class Assembler:
    def __init__(self, store, retriever, profile):
        self.store = store
        self.retriever = retriever
        self.profile = profile

    def _tok(self, text):
        return int(len(text) / CHARS_PER_TOK) + 1

    def build(self, query, session_id, budget_tokens=1500,
              working_turns=8, board_card=""):
        budget_chars = int(budget_tokens * CHARS_PER_TOK)
        parts = []
        used = 0

        def add(label, text):
            nonlocal used
            if not text:
                return False
            t = self._tok(text)
            if used + t > budget_tokens:
                return False
            parts.append((label, text))
            used += t
            return True

        # 1. core
        core = self.profile.render()
        add("core", core)

        # 1b. board (structured, provenance-aware knowledge)
        if board_card:
            add("board", board_card)

        # 2. semantic facts (query-relevant)
        facts = self.store.facts_for(self._query_subject(query), limit=6)
        if not facts:
            facts = self.store.all_facts(limit=6)
        if facts:
            ftxt = "\n".join(
                f"- {f['subject']} {f['predicate']} {f['object']}"
                for f in facts)
            add("facts", "Known facts:\n" + ftxt)

        # 3. episodic (retrieved past turns, excluding working window)
        recent_ids = {m["id"] for m in
                      self.store.recent_messages(sid=session_id,
                                                 limit=working_turns)}
        hits = self.retriever.search(query, k=6)
        ep = [h for h in hits if h["id"] not in recent_ids]
        if ep:
            etxt = "\n".join(f"- ({h['role']}) {h['text'][:200]}"
                             for h in ep[:4])
            add("episodic", "Relevant past conversation:\n" + etxt)

        # 3b. knowledge (learned material via Coal's own recall routes)
        try:
            if used < budget_tokens * 0.7:
                from knowledge import speed as _ks
                res = _ks.cached_retrieve(query, 4)
                hits = (res.get("result") or {}).get("hits", [])
                if hits:
                    ktxt = "\n".join(f"- {(h.get('text') or '')[:240]}"
                                     for h in hits[:3] if h.get("text"))
                    if ktxt:
                        add("knowledge", "Learned knowledge:\n" + ktxt)
        except Exception:
            pass

        # 4. working memory (verbatim, always last)
        recent = self.store.recent_messages(sid=session_id,
                                            limit=working_turns)
        wtxt = "\n".join(f"{m['role']}: {m['text'][:400]}" for m in recent)
        parts.append(("working", wtxt))
        used += self._tok(wtxt)

        return {"text": self._render(parts, query),
                "tiers": [p[0] for p in parts],
                "tokens": used}

    @staticmethod
    def _query_subject(query):
        # crude subject guess: longest capitalized/noun-ish token
        toks = re.findall(r"[A-Za-z]{3,}", query)
        return toks[0] if toks else None

    def _render(self, parts, query):
        blocks = []
        for label, text in parts:
            if not text.strip():
                continue
            blocks.append(f"### {label}\n{text}")
        blocks.append(f"### user\n{query}")
        return "\n\n".join(blocks)


if __name__ == "__main__":
    # integration smoke with real store/retriever
    import os
    import sys
    import tempfile
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from memory.store import Store
    from memory.embed import Embedder
    from memory.index import VectorIndex
    from memory.retrieve import Retriever
    from memory.profile import Profile
    from memory.assemble import Assembler
    d = tempfile.mkdtemp()
    st = Store(os.path.join(d, "m.db"))
    em = Embedder()
    ix = VectorIndex(os.path.join(d, "v"), dim=em.dim)
    pr = Profile(os.path.join(d, "p.json"))
    pr.set("name", "WERU")
    pr.set_many("project", ["industrial robot arm"])
    sid = st.new_session()
    for role, txt in [("user", "my dog is named Biscuit"),
                      ("assistant", "Noted, Biscuit."),
                      ("user", "I am building an industrial robot arm")]:
        mid = st.add_message(sid, role, txt)
        ix.add(mid, em.embed(txt))
    st.add_fact("user", "pet_name", "Biscuit", 0.9)
    rt = Retriever(st, ix, em)
    a = Assembler(st, rt, pr)
    out = a.build("what is my dog's name?", sid)
    print("[assemble] tiers:", out["tiers"], "tokens:", out["tokens"])
    print("[assemble] preview:")
    print(out["text"][:400])
