"""ROX N MoE Expert Engine.

Exploits the 35B-A3B's 256-expert / 8-active routing: inventory, expert
paging/placement, per-domain serving presets, and measurement.

    from moe import inventory, placement, presets, bench
    inv = inventory.load()        # cached manifest
    stats = inventory.stats(inv)
    args = presets.resolve("chat")
"""
from __future__ import annotations

from . import inventory, placement, presets, bench

__all__ = ["inventory", "placement", "presets", "bench"]