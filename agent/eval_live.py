"""Evaluate Coal on the live local model (LM Studio/Ollama).

  python eval_live.py --n 12
"""
import argparse
import sys
import tempfile
import time

sys.path.insert(0, ".")
from qwen_backend import autodetect
from chat_v2 import CoalV2
from eval import gen_qa_variants, gen_multiturn
from hf_backend import norm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--mt", type=int, default=2)
    args = ap.parse_args()

    url, kind, model, _ = autodetect()
    if not url:
        print("no local server")
        return
    print(f"backend={kind} model={model.split(chr(92))[-1]}")

    # QA
    r = CoalV2(None, "qwen", tempfile.mkdtemp(), qwen_url=url,
              qwen_model=model)
    cases = gen_qa_variants(args.n)
    ok, t0 = 0, time.time()
    for q, a in cases:
        out, st = r.respond(q)
        g, o = norm(a), norm(out)
        hit = bool(g) and bool(o) and (g in o or o in g)
        ok += hit
        tag = "OK  " if hit else "MISS"
        print(f"  [{tag}] {q[:45]:46s} -> {out[:60]!r} (want {a})")
    print(f"QA: {ok}/{len(cases)} = {ok/len(cases):.2f} "
          f"({time.time()-t0:.0f}s)")
    r.mem.store.close()

    # multi-turn memory
    total_q, correct = 0, 0
    for c in gen_multiturn(args.mt):
        r = CoalV2(None, "qwen", tempfile.mkdtemp(), qwen_url=url,
                  qwen_model=model)
        for user, expected in c["turns"]:
            out, st = r.respond(user)
            if expected is None:
                continue
            total_q += 1
            if norm(expected) in norm(out):
                correct += 1
            else:
                print(f"  [MISS] {user} -> {out[:60]!r} (want {expected})")
        r.mem.store.close()
    if total_q:
        print(f"multi-turn recall: {correct}/{total_q} = "
              f"{correct/total_q:.2f}")


if __name__ == "__main__":
    main()
