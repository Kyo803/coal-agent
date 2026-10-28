"""ROX N independent learning — a self-directed brain that grows on its own.

Public API:
    from learning import brain
    brain.stats()
    brain.cycle()               # one autonomous learning cycle
    brain.study("topology")     # force a topic
    brain.question("...")       # answer from what it has learned

Curiosity (the drive) lives in learning.curiosity.
"""
from __future__ import annotations

from . import (assess, curriculum, guardrails, ingest, loop, notes, planner,
               rehearse, sources, synthesize)
from .curiosity.graph import CuriosityGraph
from .curiosity.mood import Mood


class Brain:
    def __init__(self):
        self.graph = CuriosityGraph
        self.mood = Mood

    def cycle(self, topic=None, **kw):
        return loop.cycle(topic=topic, **kw)

    def study(self, topic, **kw):
        return loop.study(topic, **kw)

    def stats(self):
        return loop.stats()

    def report(self, topic):
        return assess.report(topic)

    def ask(self, question, topic=None, k=4):
        """Answer from what it has learned (RAG), not from parametric RAM."""
        ctx = ingest.rag().context(topic or question, k=k)
        from .curiosity.questions import answer
        return answer(question, ctx)

    def learn_url(self, topic, url):
        return ingest.learn_url(topic, url)


brain = Brain()

__all__ = ["brain", "Brain", "loop", "assess", "sources", "ingest",
           "notes", "planner", "rehearse", "synthesize", "curriculum",
           "guardrails"]
