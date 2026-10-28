"""ROX N self-improvement — it makes itself better, safely.

Public API:
    from selfimprove import improve
    improve.run()            # one cycle (dry-run by default)
    improve.run(dry_run=False)
    improve.status()
    improve.rollback.restore_file("tools/foo.py")

Guarantees: every change is backup-first; tool/code changes must win an
isolated experiment; core files require an explicit opt-in; a regression
is never applied.
"""
from __future__ import annotations

from . import (applier, backup, experiments, genome, hypothesis, loop,
               observer, policy, predictor, proposer, rollback, scoreboard,
               validator)


class Improver:
    run = staticmethod(loop.run)
    status = staticmethod(loop.status)
    signals = staticmethod(observer.collect)
    add_signal = staticmethod(observer.add_signal)
    genome = staticmethod(genome.snapshot)
    measure = staticmethod(scoreboard.measure)
    score = staticmethod(scoreboard.score)
    rollback = rollback
    backup = backup


improve = Improver()

__all__ = ["improve", "Improver", "loop", "observer", "policy", "genome",
           "rollback", "scoreboard"]
