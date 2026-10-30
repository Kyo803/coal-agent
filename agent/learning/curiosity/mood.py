"""Mood: the eagerness/excitement state that modulates effort and risk.

High excitement -> more exploration (novel, harder topics), longer
sessions, more questions. Boredom (repeated, unrewarding cycles) -> shifts
toward novelty. Persisted so the drive carries across reboots.
"""
from __future__ import annotations

from .. import paths

_FILE = "mood.json"

_DEFAULT = {
    "excitement": 0.4,
    "boredom": 0.2,
    "curiosity_urge": 0.5,
    "streak": 0,
    "cycles": 0,
    "last_cycle": None,
}


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class Mood:
    def __init__(self, data=None):
        self.d = dict(_DEFAULT)
        self.d.update(data or paths.load_json(_FILE, {}) or {})

    # ---- io ----
    def save(self):
        paths.save_json(_FILE, self.d)

    def reload(self):
        self.d.update(paths.load_json(_FILE, {}) or {})

    # ---- accessors ----
    @property
    def excitement(self):
        return float(self.d.get("excitement", 0.4))

    @property
    def boredom(self):
        return float(self.d.get("boredom", 0.2))

    @property
    def urge(self):
        return float(self.d.get("curiosity_urge", 0.5))

    @property
    def streak(self):
        return int(self.d.get("streak", 0))

    def exploration_bonus(self) -> float:
        """How much to favour the unexplored frontier this cycle."""
        return _clamp(0.25 + 0.5 * self.excitement + 0.3 * self.boredom)

    def effort(self) -> int:
        """Max sources/questions to pursue this cycle."""
        return int(2 + round(6 * self.excitement))

    # ---- transitions ----
    def cycle(self, novelty=0.5, surprise=0.0, competence=0.0,
              rewarded=True):
        e = self.excitement
        b = self.boredom
        e = _clamp(e + 0.30 * novelty + 0.25 * surprise
                   + 0.35 * competence - 0.10)
        if competence <= 0 and novelty < 0.25:
            b = _clamp(b + 0.15)
            e = _clamp(e - 0.12)
        else:
            b = _clamp(b - 0.20)
        urge = _clamp(0.5 + 0.5 * e - 0.3 * b)
        self.d.update(excitement=round(e, 3), boredom=round(b, 3),
                      curiosity_urge=round(urge, 3),
                      cycles=int(self.d.get("cycles", 0)) + 1,
                      streak=(self.streak + 1) if rewarded else 0,
                      last_cycle=paths.now())
        self.save()
        return self.d

    def describe(self) -> str:
        e = self.excitement
        mood = ("excited" if e > 0.7 else "eager" if e > 0.45
                else "curious" if e > 0.25 else "calm")
        return (f"mood={mood} excitement={e:.2f} boredom={self.boredom:.2f} "
                f"urge={self.urge:.2f} streak={self.streak} "
                f"cycles={self.d.get('cycles')}")
