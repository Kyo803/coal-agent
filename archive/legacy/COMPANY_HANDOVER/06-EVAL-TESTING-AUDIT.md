# 06 — EVALUATION + TESTING AUDIT

The proof layer. Every file documented.

---

## Test suites (run these to establish a green baseline)

| File | Purpose | Count |
|------|---------|-------|
| `test_tools.py` (16.8 KB) | Tool-layer suite: registry ≥300, 17 categories, no dup names, lazy load, permissions tiers, executor dry-run, shell-gate tiers + bypass (20 bypass attempts), intent detection, path resolution, forced-call wiring. | **145 checks** |
| `test_build.py` (4 KB) | Build capabilities (P1): language packs on disk, write-path langpack injection per extension, tool registry + intents, toolchain spec, safe self-modification (valid edit, bad-syntax reject, backup). | **38 checks** |
| `test_memory.py` (3 KB) | Phase-D gate: persistent memory must survive a new session (write fact → close → reopen → recall). | 11 checks |
| `test_board.py` (6 KB) | Detective board: store CRUD/aliases/edges/dossiers/provenance/FTS, entity resolution, builder, retrieval, RAM cache, export, queue. No model needed. | **31 checks** |
| `test_security.py` (5 KB) | Blue-team scanners: secret detection (AWS/private key/token/high-entropy), SAST rules, clean-code no-false-positives, log parse + IOC surfacing, osint. No model. | **16 checks** |
| `test_chip.py` (6 KB) | Chip design: port parsing (comma-separated), contract verification, `chip_verify` tool, iverilog compile of fixtures; `--live` also tests chip-design-ai-v4. | **9 (+2 live)** |

## `eval/` — the evaluation suite (450K deterministic cases at 100%)

| File | Purpose | Key contents |
|------|---------|--------------|
| `eval/__init__.py` (1 KB) | Package marker | Declares the suite. |
| `eval/generators.py` (8.6 KB) | Programmatic test-case generators | Every case has a *verified expected answer* — no hand-written assertions. Seeded for reproducibility. Arithmetic, safety, retrieval, fact-extraction, tool-routing, memory. |
| `eval/metrics.py` (0.9 KB) | Metrics | Accuracy / precision / recall / F1. No external deps. |
| `eval/runners.py` (7.7 KB) | Runners | Each runs the *real* Coal code (`attachments.tool_gate`, `memory.*`, `retrieval.BM25`) against generated cases. Deterministic runners + LLM runners. |
| `eval/suite.py` (7.9 KB) | Orchestrator | `python eval/suite.py --scale quick|huge --llm none|coal --llm-count N`. Runs everything, writes `eval_results.json` + a report. |
| `eval/final_report.py` (7 KB) | Report generator | `python eval/final_report.py --results eval_results.json --out EVALUATION.md` — renders the professional markdown report. |

## Root evaluation scripts

| File | Purpose |
|------|---------|
| `eval_live.py` (1.9 KB) | Evaluate Coal on the live local model (`--n 12` QA + multi-turn recall). |
| `eval_harness.py` (6.6 KB) | Standard benchmarks + QA + memory + safety in one run. |
| `evals.py` (6.8 KB) | Every PLAN §6 gate that runs without a GPU. |
| `eval_brain.py` (1.5 KB) | Before/after: base instruct vs our SFT `coal_brain` on the 36-QA set + identity. |
| `compare_all.py` (1.5 KB) | Compare all trained models on the 36-QA factuality set + identity. |
| `bench_local.py` (2.4 KB) | Local performance benchmark: latency, RAM, compute per token. |

## Reports (generated)

- `EVALUATION.md` (10.2 KB) — the full report: 450K cases 100%
  deterministic; 35B live QA/multi-turn 100%; Vulkan measurements; addenda for
  tool layer, shell security, intent-first, project awareness, image gen.
- `eval_report.md` (quick scale, 2400 cases) — short deterministic table.
- `eval_results.json`, `evals.json`, `brain_eval.json`, `model_compare.json`,
  `eval/…` outputs — raw results consumed by the report generator.

---

_Next: `07-TRAINING-PIPELINE-AUDIT.md`._