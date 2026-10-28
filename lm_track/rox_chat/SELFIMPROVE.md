# ROX N — Self-Improvement (Phase 3)

ROX N can improve its own code/config — **safely**: every change is
backed up, validated, and (for anything non-trivial) must *win an isolated
experiment* before it lands. A regression is never applied; a bad
generation can be rolled back.

## Why it is safe

- **Dry-run by default** (`selfimprove.dry_run = true`): cycles propose and
  decide, but apply nothing until you opt in.
- **Isolated experiments**: a candidate change is applied to a *temp copy*
  of the runtime core and the test suites are run there; the live tree is
  untouched (`experiments.py`).
- **Risk policy** (`policy.py`): low-risk (config/seed/langpack) may apply
  after validation; tool/code changes must pass an experiment; **core files
  (rox.py, tools/exec.py, permissions, …) require an explicit opt-in**
  (`allow_high_risk`).
- **Anti-oscillation**: a minimum interval between applied changes.
- **Backups + rollback**: every apply snapshots the file/generation;
  `rollback.restore_file` / `restore_config` restore a prior snapshot.
- **Genome**: a hashed fingerprint of the self per generation
  (`genome.py`), so changes are diffable and generation number is tracked.

## Package

```
selfimprove/
  paths.py       ~/.rox/selfimprove persistence + backup/flag paths
  genome.py      hashed snapshot of the runtime core; generations + diff
  scoreboard.py  run suites -> pass/fail score; history; compare()
  observer.py    weakness signals (stalled learning, tracebacks, failing tests)
  hypothesis.py  signals -> candidate improvements
  predictor.py   risk/scope/confidence before acting
  proposer.py    hypothesis -> concrete safe change (seeds / staged code)
  validator.py   static checks (py_compile, json)
  policy.py      dry-run / rate-limit / experiment / opt-in decisions
  experiments.py temp-copy apply + suite run + score compare
  backup.py      snapshot file/config + genome
  rollback.py    restore file/config from a snapshot
  applier.py     land an approved change (backup -> validate -> flag restart)
  loop.py        observe -> hypothesise -> predict -> propose -> validate
                 -> policy -> (experiment) -> apply -> record
```

## Cycle

`learning_stalled` (last 5 learning cycles found no sources) → keep the
curiosity frontier seeded. `tests_failing` / `runtime_error` → stage a code
fix (requires target + experiment + opt-in). `user_correction` → stage a
persona tweak.

## Tools (category `self`) + CLI

`improve_run`, `improve_status`, `improve_signals`, `improve_rollback`.

```
python rox.py --improve-status     # genome, scoreboard, signals, snapshots
python rox.py --improve            # one cycle (dry-run)
```

## Config (`config.json` -> `selfimprove`)

`dry_run` (true), `allow_high_risk` (false), `use_experiment` (true),
`max_per_cycle` (2), `min_interval_s` (300).

## Verified

`test_selfimprove.py` — 26 checks (scoreboard, genome/diff, policy tiers,
predictor, validator, hypothesis/proposer, observer, isolated experiment,
applier dry-run) all pass. Live: a dry-run cycle with a seeded signal
produced a valid low-risk proposal and correctly held at dry-run; the
regression suite stays green (145/26/25/16/9/31).
