"""ROX N persistent local memory. No cloud, no network, all on disk.

Tiers (CoALA/MemGPT-inspired):
  core      -> profile.json  (always in prompt)
  working   -> current session tail (verbatim)
  episodic  -> past turns, semantic search
  semantic  -> extracted facts/entities
  knowledge -> user docs + domain data

Entry points:
  from memory import Memory
  m = Memory("~/.rox")
  m.add_turn("user", "my dog is Biscuit")
  ctx = m.assemble("what is my dog's name?")
"""
from .store import Store
from .embed import Embedder
from .index import VectorIndex
from .retrieve import Retriever
from .consolidate import Consolidator
from .profile import Profile
from .assemble import Assembler

__all__ = ["Memory", "Store", "Embedder", "VectorIndex", "Retriever",
           "Consolidator", "Profile", "Assembler"]


class Memory:
    def __init__(self, root="~/.rox", embed_dim=384):
        import os
        self.in_memory = root == ":memory:"
        self.root = root
        if self.in_memory:
            self.store = Store(":memory:")
            self.embedder = Embedder(dim=embed_dim)
            self.index = VectorIndex(None, dim=self.embedder.dim)
            self.profile = Profile(None)
        else:
            self.root = os.path.expanduser(root)
            os.makedirs(self.root, exist_ok=True)
            self.store = Store(os.path.join(self.root, "memory.db"))
            self.embedder = Embedder(dim=embed_dim)
            self.index = VectorIndex(os.path.join(self.root, "vectors"),
                                     dim=self.embedder.dim)
            self.profile = Profile(os.path.join(self.root, "profile.json"))
        self.retriever = Retriever(self.store, self.index, self.embedder)
        self.consolidator = Consolidator(self.store, self.embedder,
                                         self.index)
        self.assembler = Assembler(self.store, self.retriever,
                                   self.profile)
        self.session_id = self.store.new_session()

    def add_turn(self, role, text, s_mean=0.0, thinking=None):
        mid = self.store.add_message(self.session_id, role, text, s_mean,
                                     thinking=thinking)
        vec = self.embedder.embed(text)
        self.index.add(mid, vec, kind="message")
        return mid

    def assemble(self, query, budget_tokens=1500, board_card=""):
        return self.assembler.build(query, self.session_id,
                                    budget_tokens=budget_tokens,
                                    board_card=board_card)

    def consolidate(self):
        """Call at session end or every N turns."""
        return self.consolidator.run(self.session_id, self.profile)

    def remember(self, text, kind="fact"):
        mid = self.store.add_message(self.session_id, "note", text, 0.0)
        self.index.add(mid, self.embedder.embed(text), kind=kind)
        return mid

    def search(self, query, k=8):
        return self.retriever.search(query, k=k)
