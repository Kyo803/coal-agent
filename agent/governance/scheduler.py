"""Scheduler: decide what the autonomous brain should do right now.

Cadence is idle/night/always-on: background work only happens when the
user is idle; night runs more learning cycles; improvement runs only if
enabled.
"""
from __future__ import annotations

import time

from coal_config import cfg


def gc() -> dict:
    return cfg.get("governance", {}) or {}


def phase(now=None) -> str:
    h = (now or time.localtime()).tm_hour
    ns = int(gc().get("night_start", 0))
    ne = int(gc().get("night_end", 7))
    if ns <= ne:
        return "night" if ns <= h < ne else "day"
    return "night" if (h >= ns or h < ne) else "day"


def plan(idle_now: bool = True, now=None) -> list:
    g = gc()
    if not g.get("enabled", False):
        return []
    tasks = []
    ph = phase(now)
    if not idle_now:
        return tasks
    if g.get("run_learning", True):
        n = int(g.get("night_cycles", 3)) if ph == "night" \
            else int(g.get("learning_cycles", 1))
        tasks += [{"task": "study"}] * max(1, n)
    if g.get("run_observe", True):
        tasks.append({"task": "observe"})
    if g.get("run_practice", False) and ph == "night":
        tasks.append({"task": "practice"})
    if g.get("run_reflect", True) and ph == "night":
        tasks.append({"task": "reflect"})
    if g.get("run_improve", False):
        tasks.append({"task": "improve"})
    if g.get("run_archive", True):
        tasks.append({"task": "archive"})
    if g.get("run_mission_queue", True):
        tasks.append({"task": "mission_queue"})
    if ph == "night" and g.get("run_retry_missions", True):
        tasks.append({"task": "mission_retry"})
    return tasks
