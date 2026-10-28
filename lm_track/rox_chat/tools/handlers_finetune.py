"""Fine-tune tool handlers (plan + export the QLoRA bundle)."""
from __future__ import annotations

import json


def finetune_plan(args, ctx):
    from finetune import tune
    return {"ok": True, "output": json.dumps(tune.plan(), indent=1,
                                             default=str)}


def finetune_export(args, ctx):
    from finetune import tune
    man = tune.export(args.get("dir"))
    return {"ok": True, "output": json.dumps(man, indent=1, default=str)}
