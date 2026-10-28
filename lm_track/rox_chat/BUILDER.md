# ROX N — Builder (Phase 4)

The extreme-coding machine: a goal becomes a verified product through a
real feedback loop, **inside the isolated sandbox**.

```
PLAN/SPEC -> CONTRACT-aware GENERATE (freeze verified units)
          -> COMPILE  (diagnose -> patch -> recompile, loop)
          -> TEST
          -> ACCEPTANCE (artifacts + criteria)
          -> OPTIMIZE (quantum-inspired design search)
          -> POLISH (format/lint) -> DONE
```

Whenever a safe patch isn't possible the loop escalates to the
**restructurer** (re-plan/regenerate) instead of thrashing. All state is
checkpointed, so builds resume.

## Package

```
builder/
  objectives.py        the brain chooses quality objectives (per stack fallback)
  optimizer.py         quantum-inspired search (amplitude amplification + Pareto)
  planner.py           description -> build spec + file manifest
  contract.py          unit exports/imports; interface drift detection
  generator.py         contract-aware unit generation (35B server)
  freezer.py           verified units frozen by hash; regenerated only on iface change
  compiler.py          build in the sandbox (node/vite/next/ts/py/hdl/rust/go)
  diagnoser.py         classify errors (syntax/type/interface/test/runtime/dependency)
  patcher.py           surgical fixes; None => escalate
  tester.py            run tests in the sandbox (skips when none)
  verifier_ui.py       build artifact presence + optional playwright screenshot
  requirements_check.py  acceptance criteria (file:/contains:/runs:)
  restructurer.py      re-plan when the product still isn't right
  polisher.py          formatters/linters (best-effort)
  checkpoints.py       save/resume build state
  loop.py              the state machine (run / repair / generate_project)
```

## Quantum-inspired optimizer (honest)

`optimizer.py` represents candidate designs as a **state vector of
amplitudes`, scores them with an **energy** over the chosen objectives,
and concentrates probability with **amplitude amplification** (Grover-style
oracle + diffusion). It returns the best design, the **Pareto frontier**,
and per-design energies/probabilities. These are classical algorithms in
the quantum metaphor — no quantum hardware.

## Tools (category `build`) + CLI

`builder_run`, `builder_objectives`, `builder_diagnose`, `builder_optimize`.

```
# repair/verify an existing sandbox project:
python rox.py --build NAME DIR --stack python \
    --criteria "file:/home/rox/work/p/main.py,contains:def main"
```

## Verified

`test_builder.py` — 20 checks (objectives, optimizer, contract, diagnoser,
freezer, restructurer, requirements) pass. Live: the builder ran in the
sandbox on a real project — **compiled** (`python3 -m compileall`),
**tested** (no-tests → skip), passed **acceptance** criteria, and
**polished** — with all state checkpointed.

## Wiring still to complete

- Drive `generate_project` with the 35B server running for a full
  plan → generate → build from one description (the path exists; it just
  needs the model up).
- Optional playwright screenshot into acceptance.
