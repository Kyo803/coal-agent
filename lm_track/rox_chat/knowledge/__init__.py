"""ROX N knowledge mechanics — recall routes, indexing, skills, speed.

Public API:
    from knowledge import mind
    mind.retrieve("query")          # bandit-chosen retrieval route
    mind.ingest("path-or-url")      # read + index any format
    mind.compress("topic")          # distill notes into concepts
    mind.skill_from_notes("topic")  # turn knowledge into a reusable skill
    mind.stats()                    # router/speed/compression/skills
"""
from __future__ import annotations

from . import (compression, curriculum, mechanics, paths, reader, rehearsal,
               router, skill, speed)


class Knowledge:
    retrieve = staticmethod(router.retrieve)
    ingest = staticmethod(reader.ingest)
    read = staticmethod(reader.read_source)
    compress = staticmethod(compression.compress)
    rehearse = staticmethod(rehearsal.rehearse)
    sequence = staticmethod(curriculum.sequence)
    skill_from_notes = staticmethod(skill.from_notes)
    skill_add = staticmethod(skill.add)
    skill_get = staticmethod(skill.get)
    list_skills = staticmethod(skill.list_skills)
    cache = staticmethod(speed.cached_retrieve)

    def stats(self) -> dict:
        return {"router": router.stats(), "speed": speed.stats(),
                "compression": compression.stats(),
                "mechanics": mechanics.stats(),
                "skills": skill.list_skills()}


mind = Knowledge()

__all__ = ["mind", "Knowledge", "router", "mechanics", "compression",
           "speed", "skill", "reader", "rehearsal", "curriculum"]
