"""Curiosity — Coal's intrinsic drive to learn.

The brain is not told what to study; it decides from an internal reward
made of novelty, curiosity (frontier proximity), competence gain, and
surprise, modulated by an "eagerness/excitement" mood. This is what makes
it explore on its own.
"""
from __future__ import annotations

from .graph import CuriosityGraph
from .drive import reward, rank
from .mood import Mood
from .questions import generate_questions
from .tension import contradictions, surprise

__all__ = ["CuriosityGraph", "reward", "rank", "Mood",
           "generate_questions", "contradictions", "surprise"]
