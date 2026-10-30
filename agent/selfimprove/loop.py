"""The self-improvement loop.

observe -> hypothesise -> predict -> propose -> validate -> policy -> (experiment) -> apply -> record.

Safe by default: dry-run, isolated experiments for tool/code changes, and
an explicit opt-in for core files. A regression is caught by the
experiment/scoreboard and the change is never applied.
"""
from __future__ import annotations

import time

from coal_config import cfg

from . import (applier, backup, experiments, genome, hypothesis, observer,
               paths, policy, predictor, proposer, scoreboard, validator)


def _sc():
    return cfg.get("selfimprove", {}) or {}


def _llm_ok() -> bool:
    try:
        from learning import llm
        return llm.available()
    except Exception:
        return False


def run(dry_run: bool | None = None, allow_high_risk: bool | None = None,
        use_experiment: bool | None = None) -> dict:
    sc = _sc()
    if dry_run is None:
        dry_run = bool(sc.get("dry_run", True))
    if allow_high_risk is None:
        allow_high_risk = bool(sc.get("allow_high_risk", False))
    if use_experiment is None:
        use_experiment = bool(sc.get("use_experiment", True))
    maxc = int(sc.get("max_per_cycle", 2))
    llm_ok = _llm_ok()

    sigs = observer.collect()
    hyps = hypothesis.from_signals(sigs)
    results = []
    for h in hyps[:maxc]:
        pred = predictor.predict(h)
        entry = {"hypothesis": h, "prediction": pred}
        if not pred.get("worth_it", True):
            entry["result"] = "predicted gain too low"
            results.append(entry)
            continue
        prop = proposer.propose(h, llm_ok=llm_ok)
        if not prop:
            entry["result"] = "no safe proposal"
            results.append(entry)
            continue
        okv, why = validator.validate_change(prop)
        entry.update({"change": prop, "valid": okv, "validator": why})

        dec = policy.decide(h, dry_run=dry_run,
                            allow_high_risk=allow_high_risk)
        if dec["action"] == "experiment" and use_experiment and not dry_run:
            exp = experiments.run(prop)
            entry["experiment"] = {"passed": exp["passed"],
                                   "compare": exp.get("compare")}
            dec = policy.decide(h, dry_run=dry_run,
                                allow_high_risk=allow_high_risk,
                                experiment_passed=exp["passed"])
        entry["decision"] = dec
        if dec["action"] == "apply" and okv and not dry_run:
            entry["generation_before"] = backup.snapshot_genome().get(
                "generation")
            entry["applied"] = applier.apply(prop)
        results.append(entry)

    gen = genome.current() if dry_run else genome.record()
    rep = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "dry_run": dry_run,
           "signals": [s.get("kind") for s in sigs],
           "hypotheses": len(hyps), "results": results,
           "generation": gen.get("generation")}
    paths.append_jsonl("cycles.jsonl", {
        "ts": rep["ts"], "dry_run": dry_run, "signals": rep["signals"],
        "applied": sum(1 for r in results
                       if (r.get("applied") or {}).get("ok"))})
    return rep


def status() -> dict:
    return {"genome": genome.current(),
            "scoreboard": scoreboard.last(),
            "signals": [s.get("kind") for s in observer.collect()],
            "snapshots": backup.list_snapshots(5),
            "history": scoreboard.history(5)}


if __name__ == "__main__":
    import json
    print(json.dumps(run(dry_run=True), indent=1, default=str))
