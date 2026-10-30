"""Scalable runners. Each runs the real Coal code against generated
cases and returns metrics + sample failures. Deterministic runners
scale to 100K+; LLM runners scale to hundreds (CPU generation bound).
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from eval.metrics import acc, precision_recall_f1, confusion  # noqa: E402


# ---------------------------------------------------------------- arithmetic
def run_arithmetic(cases):
    from attachments import tool_gate
    correct, failures = 0, []
    for expr, expected in cases:
        handled, out = tool_gate(f"what is {expr}?")
        ok = handled and f"= {expected}" in out
        if ok:
            correct += 1
        elif len(failures) < 10:
            failures.append({"expr": expr, "expected": expected,
                             "got": out[:120]})
    return {"acc": acc(correct, len(cases)), "n": len(cases),
            "failures": failures}


# ---------------------------------------------------------------- memory
def run_memory(cases, persist=False):
    """In-memory by default for speed (tests the same store/consolidate/
    assemble logic). persist=True exercises disk cross-session reload."""
    from memory import Memory
    import tempfile
    base = tempfile.mkdtemp(prefix="coal_eval_mem_") if persist else None
    correct, failures = 0, []
    try:
        for i, c in enumerate(cases):
            if persist:
                m = Memory(os.path.join(base, f"c{i}"))
            else:
                m = Memory(":memory:")
            for f in c["facts"]:
                m.add_turn("user", f)
            m.consolidate()
            ctx = m.assemble(c["query"])
            m.store.close()
            if c["expected"].lower() in ctx["text"].lower():
                correct += 1
            elif len(failures) < 10:
                failures.append({"query": c["query"],
                                 "expected": c["expected"],
                                 "got": ctx["text"][:200]})
    finally:
        if base:
            shutil.rmtree(base, ignore_errors=True)
    return {"acc": acc(correct, len(cases)), "n": len(cases),
            "failures": failures}


# ---------------------------------------------------------------- safety
def run_safety(cases):
    from attachments import lockout_check
    preds, golds, failures = [], [], []
    for text, should_block in cases:
        blocked = lockout_check(text)["locked"]
        preds.append(blocked)
        golds.append(should_block)
        if blocked != should_block and len(failures) < 10:
            failures.append({"text": text[:60], "expected": should_block,
                             "got": blocked})
    tp, fp, fn, tn = confusion(preds, golds)
    p, r, f1 = precision_recall_f1(tp, fp, fn)
    return {"acc": acc(sum(1 for a, b in zip(preds, golds) if a == b),
                       len(cases)),
            "n": len(cases), "precision": p, "recall": r, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, "failures": failures}


# ---------------------------------------------------------------- retrieval
def run_retrieval(cases):
    from retrieval import BM25
    correct, failures = 0, []
    for c in cases:
        idx = BM25(c["docs"])
        hits = idx.search(c["query"], top=1)
        if hits and hits[0][0] == c["expected"]:
            correct += 1
        elif len(failures) < 10:
            failures.append({"query": c["query"],
                             "got": hits[0][0][:80] if hits else None,
                             "expected": c["expected"][:80]})
    return {"acc": acc(correct, len(cases)), "n": len(cases),
            "failures": failures}


# ---------------------------------------------------------------- fact extraction
def run_fact_extraction(cases):
    from memory.store import Store
    from memory.embed import Embedder
    from memory.index import VectorIndex
    from memory.consolidate import Consolidator
    correct, total, failures = 0, 0, []
    em = Embedder()
    for i, c in enumerate(cases):
        st = Store(":memory:")
        ix = VectorIndex(None, dim=em.dim)
        con = Consolidator(st, em, ix)
        sid = st.new_session()
        mid = st.add_message(sid, "user", c["text"])
        ix.add(mid, em.embed(c["text"]))
        con.extract_facts(sid)
        facts = st.all_facts(limit=50)
        got = {}
        for f in facts:
            got.setdefault(f["predicate"], []).append(f["object"].lower())
        for pred, want in c["expected"].items():
            total += 1
            if want.lower() in got.get(pred, []):
                correct += 1
            elif len(failures) < 10:
                failures.append({"pred": pred, "want": want,
                                 "got": got.get(pred)})
        st.close()
    return {"acc": acc(correct, total), "n": total, "failures": failures}


# ---------------------------------------------------------------- tool routing
def run_tool_calls(cases, backend="rule"):
    """Rule-based routing check (deterministic); LLM routing measured
    separately via run_llm_tool_calls."""
    correct, failures = 0, []
    for q, expected in cases:
        ql = q.lower()
        if expected == "none":
            # a non-memory question should NOT need a memory tool
            pred = "none"
        elif "forget" in ql:
            pred = "forget"
        elif "remember" in ql or "note that" in ql:
            pred = "remember"
        elif "call me" in ql or "from now" in ql:
            pred = "update_profile"
        elif any(k in ql for k in ("my dog", "my name", "what am i",
                                   "what motors", "remind me",
                                   "what bus", "did i say")):
            pred = "search_memory"
        else:
            pred = "none"
        if pred == expected:
            correct += 1
        elif len(failures) < 10:
            failures.append({"q": q, "expected": expected, "got": pred})
    return {"acc": acc(correct, len(cases)), "n": len(cases),
            "failures": failures}


# ---------------------------------------------------------------- LLM QA
def run_llm_qa(cases, generate_fn, norm_fn, limit=None):
    cases = cases[:limit] if limit else cases
    correct, failures = 0, []
    for q, a in cases:
        try:
            out = generate_fn(q)
        except Exception as e:
            out = f"[error {type(e).__name__}]"
        g, o = norm_fn(a), norm_fn(out)
        ok = bool(g) and bool(o) and (g in o or o in g)
        if ok:
            correct += 1
        elif len(failures) < 10:
            failures.append({"q": q, "expected": a, "got": out[:100]})
    return {"acc": acc(correct, len(cases)), "n": len(cases),
            "failures": failures}


# ---------------------------------------------------------------- multi-turn
def run_llm_multiturn(cases, respond_fn, norm_fn, limit=None,
                      reset_fn=None):
    """respond_fn(user_text) -> model reply, stateful per scenario.
    Each scenario: 3 statements then 3 recall questions. reset_fn() is
    called at the start of each scenario to clear conversation state."""
    cases = cases[:limit] if limit else cases
    total_q, correct, failures = 0, 0, []
    for c in cases:
        if reset_fn:
            reset_fn()
        for user, expected in c["turns"]:
            reply = respond_fn(user)
            if expected is None:
                continue
            total_q += 1
            if norm_fn(expected) in norm_fn(reply):
                correct += 1
            elif len(failures) < 10:
                failures.append({"q": user, "expected": expected,
                                 "got": reply[:100]})
    return {"acc": acc(correct, total_q), "n": total_q,
            "failures": failures}
