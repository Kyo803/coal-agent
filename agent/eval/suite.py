"""Coal evaluation suite: run everything, produce a report.

  python eval/suite.py --scale full          # 100K+ deterministic cases
  python eval/suite.py --scale quick         # fast smoke
  python eval/suite.py --scale full --llm hf # + LLM conversation tests

Deterministic tests (arithmetic, safety, retrieval, facts, tools, memory)
scale to 100K+. LLM tests (QA, multi-turn, tool routing) run at hundreds
because generation is CPU-bound.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from eval import generators as G  # noqa: E402
from eval import runners as R  # noqa: E402

SCALES = {
    "quick": {"arith": 500, "safety": 500, "retr": 200, "fact": 200,
              "tool": 500, "mem": 100, "llm": 30},
    "full": {"arith": 50000, "safety": 20000, "retr": 20000, "fact": 20000,
             "tool": 20000, "mem": 20000, "llm": 200},
    "huge": {"arith": 100000, "safety": 50000, "retr": 50000, "fact": 50000,
             "tool": 50000, "mem": 50000, "llm": 300},
}


def make_llm_fns(backend, model_path=None):
    """Return (generate_fn, respond_fn, norm_fn) for LLM tests."""
    from hf_backend import norm

    if backend == "hf":
        from hf_backend import HFDraft
        d = HFDraft()

        def gen(q):
            d.history = []
            txt, _, _, _ = d.draft_fn(q)
            return txt

        def respond(q):
            txt, _, _, _ = d.draft_fn(q)
            return txt

        def reset():
            d.history = []
        return gen, respond, norm, reset

    if backend == "qwen":
        from qwen_backend import QwenBackend, autodetect
        from memory.tools import MemoryTools
        from memory import Memory
        url, kind, model, _ = autodetect()
        b = QwenBackend(base_url=url or "http://localhost:1234/v1",
                        model=model or "qwen3.6-35b-a3b")
        mem = Memory(":memory:")
        tools = MemoryTools(mem)

        def gen(q):
            txt, _ = b.chat_with_tools(q, tools)
            return txt

        def respond(q):
            txt, _ = b.chat_with_tools(q, tools)
            return txt
        return gen, respond, norm, None

    if backend == "coal":
        # FULL Coal pipeline: memory-wired chat (memory + model)
        from chat_v2 import CoalV2
        import tempfile
        root = tempfile.mkdtemp(prefix="coal_eval_llm_")
        r = CoalV2(None, "hf", root)

        def gen(q):
            out, _ = r.respond(q)
            return out

        def respond(q):
            out, _ = r.respond(q)
            return out

        def reset():
            # fresh session + memory for each scenario
            import shutil
            r.mem.store.close()
            shutil.rmtree(root, ignore_errors=True)
            os.makedirs(root, exist_ok=True)
            r.mem = type(r.mem)(root)
            from memory.tools import MemoryTools
            r.tools = MemoryTools(r.mem)
        return gen, respond, norm, reset

    if backend == "v2":
        from local_run import load_model, generate
        m, _ = load_model(model_path)

        def gen(q):
            return generate(m, None, q, max_new=40)

        def respond(q):
            return generate(m, None, q, max_new=40)
        return gen, respond, norm, None

    return None, None, norm, None


def run_suite(scale="full", llm="hf", model_path=None, verbose=True,
              llm_count=None):
    cfg = dict(SCALES[scale])
    if llm_count is not None:
        cfg["llm"] = llm_count
    t0 = time.time()
    res = {"scale": scale, "config": cfg, "started": time.time()}

    def log(msg):
        if verbose:
            print(msg, flush=True)

    log(f"[suite] scale={scale} deterministic cases="
        f"{sum(cfg[k] for k in ('arith','safety','retr','fact','tool','mem'))}")

    log("  arithmetic ...")
    res["arithmetic"] = R.run_arithmetic(G.gen_arithmetic(cfg["arith"]))
    log(f"    acc={res['arithmetic']['acc']}")

    log("  safety ...")
    res["safety"] = R.run_safety(G.gen_safety(cfg["safety"]))
    log(f"    acc={res['safety']['acc']} f1={res['safety']['f1']}")

    log("  retrieval ...")
    res["retrieval"] = R.run_retrieval(G.gen_retrieval(cfg["retr"]))
    log(f"    acc={res['retrieval']['acc']}")

    log("  fact_extraction ...")
    res["fact_extraction"] = R.run_fact_extraction(
        G.gen_fact_extraction(cfg["fact"]))
    log(f"    acc={res['fact_extraction']['acc']}")

    log("  tool_routing (rule) ...")
    res["tool_routing"] = R.run_tool_calls(G.gen_tool_calls(cfg["tool"]))
    log(f"    acc={res['tool_routing']['acc']}")

    log("  memory ...")
    res["memory"] = R.run_memory(G.gen_memory(cfg["mem"]))
    log(f"    acc={res['memory']['acc']}")

    if llm:
        gen, respond, norm, reset = make_llm_fns(llm, model_path)
        if gen:
            log(f"  llm_qa ({llm}, n={cfg['llm']}) ...")
            res["llm_qa"] = R.run_llm_qa(G.gen_qa_variants(cfg["llm"]),
                                         gen, norm)
            log(f"    acc={res['llm_qa']['acc']}")
            log(f"  llm_multiturn ({llm}, n={max(10, cfg['llm'] // 4)}) ...")
            res["llm_multiturn"] = R.run_llm_multiturn(
                G.gen_multiturn(max(10, cfg["llm"] // 4)), respond, norm,
                reset_fn=reset)
            log(f"    acc={res['llm_multiturn']['acc']}")

    res["wall_seconds"] = round(time.time() - t0, 1)
    total_cases = sum(res[k]["n"] for k in res
                      if isinstance(res[k], dict) and "n" in res[k])
    res["total_cases"] = total_cases
    log(f"[suite] done: {total_cases} cases in {res['wall_seconds']}s")
    return res


def write_report(res, path):
    lines = ["# Coal Evaluation Report", "",
             f"_scale={res['scale']} · {res['total_cases']} cases · "
             f"{res['wall_seconds']}s wall_", "",
             "## Deterministic features", "",
             "| Feature | Cases | Accuracy | Precision | Recall | F1 |",
             "|---|---|---|---|---|---|"]
    for k in ("arithmetic", "safety", "retrieval", "fact_extraction",
              "tool_routing", "memory"):
        r = res.get(k)
        if not r:
            continue
        lines.append(f"| {k} | {r['n']} | {r['acc']} | "
                     f"{r.get('precision','-')} | {r.get('recall','-')} | "
                     f"{r.get('f1','-')} |")
    if "llm_qa" in res or "llm_multiturn" in res:
        lines += ["", "## LLM conversation", "",
                  "| Test | Cases | Accuracy |", "|---|---|---|"]
        for k in ("llm_qa", "llm_multiturn"):
            if k in res:
                lines.append(f"| {k} | {res[k]['n']} | {res[k]['acc']} |")
    lines += ["", "## Sample failures", ""]
    for k in res:
        r = res.get(k)
        if isinstance(r, dict) and r.get("failures"):
            lines.append(f"### {k}")
            for f in r["failures"][:5]:
                lines.append(f"- {json.dumps(f)[:220]}")
            lines.append("")
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="quick", choices=list(SCALES))
    ap.add_argument("--llm", default="hf", choices=["hf", "qwen", "v2", "none"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "eval_report.md"))
    ap.add_argument("--llm-count", type=int, default=None)
    args = ap.parse_args()
    res = run_suite(args.scale, args.llm, args.model,
                    llm_count=args.llm_count)
    json.dump(res, open(os.path.join(ROOT, "eval_results.json"), "w"),
              indent=1)
    p = write_report(res, args.out)
    print(f"[suite] report -> {p}")


if __name__ == "__main__":
    main()
