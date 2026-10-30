"""The Independent Brain facade: drive + mood + graph + activities."""
from __future__ import annotations

from . import activities


class Brain:
    def __init__(self):
        from learning.curiosity.graph import CuriosityGraph
        from learning.curiosity.mood import Mood
        self.graph = CuriosityGraph()
        self.mood = Mood()

    def focus(self) -> str | None:
        from learning.curiosity.drive import rank
        r = rank(self.graph, self.mood, n=1)
        return r[0][0] if r else None

    def status(self) -> dict:
        return {"mood": self.mood.describe(), "graph": self.graph.stats(),
                "focus": self.focus()}

    # activity dispatch
    def act(self, name: str, **kw) -> dict:
        return activities.run(name, **kw)

    study = staticmethod(activities.study)
    observe = staticmethod(activities.observe)
    practice = staticmethod(activities.practice)
    reflect = staticmethod(activities.reflect)
    improve = staticmethod(activities.improve)
    archive = staticmethod(activities.archive)


brain = Brain()
