"""Export the fine-tune bundle (dataset + script + runbook + manifest)."""
from __future__ import annotations

import json
import os
import shutil

from . import cookbook, dataset, plan


def export(out_dir: str | None = None) -> dict:
    d = out_dir or dataset.dir()
    os.makedirs(d, exist_ok=True)
    ds = dataset.write()
    dataset_path = ds["path"]
    if os.path.abspath(os.path.dirname(dataset_path)) != os.path.abspath(d):
        dataset_path = os.path.join(d, "dataset.jsonl")
        shutil.copy2(ds["path"], dataset_path)

    script_p = os.path.join(d, "train_qlora.py")
    with open(script_p, "w", encoding="utf-8") as f:
        f.write(cookbook.train_script())
    book_p = os.path.join(d, "RUNBOOK.md")
    with open(book_p, "w", encoding="utf-8") as f:
        f.write(cookbook.runbook())

    manifest = {"dataset": dataset_path, "examples": ds["count"],
                "base_model": cookbook.base_model(),
                "script": script_p, "runbook": book_p,
                "estimate": plan.estimate(ds["count"])}
    mp = os.path.join(d, "manifest.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    return manifest
