"""Task-Specialization Router (Structure 3).

    from specialization import route
    cfg = route("build a 16-bit cpu in verilog")   # -> chip profile
"""
from __future__ import annotations

from . import registry

route = registry.route
classify = registry.classify
FAMILIES = registry.FAMILIES

__all__ = ["route", "classify", "FAMILIES"]
