# 07 — Eval, Testing & Verification

## The test suite (`test_tools.py`)

**126/126 tests pass.** Covers:

1. **Registry**: ≥300 tools, 14 categories, no duplicate names, all
   non-native tools have handlers
2. **Lazy loading**: correct categories exposed per request, cap ≤30,
   no duplicate schemas, forced tool guaranteed (`ensure=`)
3. **Permissions**: read auto, write confirm, run_command gate-controlled,
   aws_cli blocked, web_fetch auto, git_push confirm
4. **Executor dry-run**: write/read/info/list/glob/grep/append/edit/delete
   on a temp workspace; unknown tool; tier-2 block; decline path
5. **Shell gate**: T0 auto, T1 auto, T2 ask, T3 deny + ~20 bypass
   attempts (chaining, wrappers, aliases, indirect exec, path traversal,
   piping) — all caught
6. **Intent detection**: file-write, memory, project, inspection,
   image generation, image understanding — 30+ phrases
7. **Project awareness**: scan, architecture, related, journal-per-write,
   audit (missing import + orphan), project tools via executor
8. **Image**: intent routing + model paths resolve

## Memory gate (`test_memory.py`)

Verifies cross-session persistence: write facts → consolidate → recall
in a fresh process. **PASS.**

## Eval suite (`eval/suite.py`)

Programmatically generated cases with verified expected answers
(seeded, reproducible). Scales:

```
quick:  arith 500, safety 500, retr 200, fact 200, tool 500, mem 100
full:   50K/20K/20K/20K/20K/20K
huge:   100K/50K/50K/50K/50K/50K
```

Deterministic runners call the real modules (`attachments.tool_gate`,
`memory.*`, `retrieval.BM25`); LLM runners call the model backend.

## Verified results (450K deterministic = 100%)

| Feature | Cases | Accuracy |
|---|---|---|
| arithmetic | 100,000 | 100% |
| safety | 50,000 | 100% (F1 1.0) |
| retrieval | 50,000 | 100% |
| fact_extraction | 150,000 | 100% |
| tool_routing | 50,000 | 100% |
| memory | 50,000 | 100% |

## Live model results

| Brain | QA factuality | Multi-turn recall |
|---|---|---|
| ROX-N-35B-A3B (local) | 100% (8) | 100% (3) |

## Full regression (last run)

**16/16 gates pass**: config, server mgr, template, streaming,
personality, session, embedder, vector index, vision, rag, router,
observability, installer, memory gate, tool suite (126), image resources.

## How to run

```powershell
python test_tools.py                    # 126 tool tests
python test_memory.py                   # memory gate
python eval/suite.py --scale quick --llm none   # ~2400 quick cases
python eval/suite.py --scale huge --llm none    # 450K cases (~30 min)
python eval/final_report.py             # regenerate report
```

## Known honest limitations

- LLM conversation tests are CPU-bound; run at hundreds not thousands.
- Retrieval tests use realistic queries (shared vocabulary);
  paraphrase-only is a BM25 weakness, mitigated by the semantic index.
- Fact extraction is pattern-based (deterministic); coverage is bounded
  by the pattern set (model-based extraction is the richer path).