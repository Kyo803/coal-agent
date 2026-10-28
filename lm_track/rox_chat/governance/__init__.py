"""ROX N governance — resources, cadence, telemetry, and the daemon.

Public API:
    from governance import gov
    gov.tick()            # one autonomous decision cycle
    gov.daemon(once=True) # run one tick
    gov.health()          # server/ollama/sandbox status
    gov.summary()         # telemetry + satisfaction
    gov.touch()           # mark user activity (heartbeat)
"""
from __future__ import annotations

from . import daemon as _daemon
from . import health as _health
from . import paths as _paths
from . import resource as _resource
from . import scheduler as _scheduler
from . import telemetry as _telemetry


class Gov:
    tick = staticmethod(_daemon.tick)
    daemon = staticmethod(_daemon.daemon)
    touch = staticmethod(_daemon.touch_heartbeat)
    health = staticmethod(_health.snapshot)
    healthy = staticmethod(_health.ok)
    summary = staticmethod(_telemetry.summary)
    satisfaction = staticmethod(_telemetry.satisfaction)
    metrics = staticmethod(_telemetry.generation_metrics)
    record = staticmethod(_telemetry.record)
    resources = staticmethod(_resource.summary)
    park = staticmethod(_resource.park_35b)
    resume = staticmethod(_resource.resume_35b)
    phase = staticmethod(_scheduler.phase)


gov = Gov()

__all__ = ["gov", "Gov"]
