"""The Independent Brain: autonomous, self-directed, always-on.

    from autonomy import brain
    brain.status()            # mood + curiosity graph + current focus
    brain.study("topology")   # read/ingest a topic
    brain.observe()           # find + ingest a source on its own
    brain.practice()          # build a small project in the sandbox
    brain.reflect()           # measure the self + board
    brain.improve()           # self-improvement cycle
    brain.act("archive")      # fold the conversation queue onto the board

    from autonomy import loop
    loop.tick()               # one autonomous decision cycle
    loop.live()               # the always-on daemon
"""
from __future__ import annotations

from . import activities, loop
from .brain import Brain, brain

__all__ = ["brain", "Brain", "activities", "loop"]
