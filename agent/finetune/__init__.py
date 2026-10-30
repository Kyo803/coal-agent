"""Coal fine-tuning hook — turn learned knowledge into weights.

Public API:
    from finetune import tune
    tune.export()        # dataset + train_qlora.py + RUNBOOK.md + manifest
    tune.plan()          # base model, dataset dir, cost/time estimate
    tune.build()         # the instruction dataset (list)
"""
from __future__ import annotations

from . import cookbook as _cookbook
from . import dataset as _dataset
from . import export as _export
from . import plan as _plan
from . import verilog_corpus as _verilog_corpus


class Tune:
    build = staticmethod(_dataset.build)
    write = staticmethod(_dataset.write)
    export = staticmethod(_export.export)
    plan = staticmethod(_plan.plan)
    estimate = staticmethod(_plan.estimate)
    runbook = staticmethod(_cookbook.runbook)
    train_script = staticmethod(_cookbook.train_script)
    base_model = staticmethod(_cookbook.base_model)
    verilog_export = staticmethod(_verilog_corpus.export)


tune = Tune()

__all__ = ["tune", "Tune"]
