"""Autonomy loop: tie the brain to the governance daemon (idle/night)."""
from __future__ import annotations


def tick(force_idle: bool = False) -> dict:
    from governance import daemon
    return daemon.tick(force_idle=force_idle)


def live(once: bool = False, max_cycles: int = 0, poll=None) -> dict:
    from governance import daemon
    return daemon.daemon(once=once, max_cycles=max_cycles, poll=poll)
