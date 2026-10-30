# builder — multi-file project loop

Plan → generate → compile → diagnose → patch, until a project runs.

`planner.py`, `generator.py`, `compiler.py`, `diagnoser.py`,
`patcher.py`, `loop.py`, `contract.py` (acceptance checks),
`checkpoints.py` / `freezer.py` (resume points), `hdl_tb.py`
(testbench generation), `missions.py` / `mission_queue.py`
(queued work), `verifier_ui.py`.

Projects are written to `~/Desktop/ROX Projects/<name>` unless an explicit
destination is given.
