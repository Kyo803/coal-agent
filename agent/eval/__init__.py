"""Coal evaluation suite.

Programmatic test generation + scalable runners + metrics + report.
Everything runs locally. Deterministic features scale to 100K+ cases;
LLM conversation tests scale to hundreds (CPU-bound generation).
"""
from .metrics import acc, precision_recall_f1, confusion, summarize
from .generators import (gen_arithmetic, gen_memory, gen_safety,
                         gen_retrieval, gen_fact_extraction, gen_qa_variants,
                         gen_multiturn, gen_tool_calls)
from .runners import (run_arithmetic, run_memory, run_safety,
                      run_retrieval, run_fact_extraction, run_tool_calls,
                      run_llm_qa, run_llm_multiturn)

__all__ = [
    "acc", "precision_recall_f1", "confusion", "summarize",
    "gen_arithmetic", "gen_memory", "gen_safety", "gen_retrieval",
    "gen_fact_extraction", "gen_qa_variants", "gen_multiturn",
    "gen_tool_calls",
    "run_arithmetic", "run_memory", "run_safety", "run_retrieval",
    "run_fact_extraction", "run_tool_calls", "run_llm_qa",
    "run_llm_multiturn",
]
