"""Measure candidate retrieval-trigger signals vs actual correctness.

Model: SmolLM2-135M-Instruct on CPU (small enough to run anywhere, weak
enough to actually make mistakes — we need wrong answers to measure).
Per question: 1 greedy decode (token probs recorded) + 3 stochastic
samples. Signals: min token prob (FLARE-style), mean logprob, and
multi-sample disagreement (discrete semantic-entropy family).
Grade: normalized containment of the gold answer. Writes results.json.
"""
import json
import math
import os
import re
import sys

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
N_SAMPLES = 3


def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def correct(out: str, gold: str) -> bool:
    o, g = norm(out), norm(gold)
    return bool(o) and bool(g) and (g in o or o in g)


def main():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    qa = json.load(open(os.path.join(HERE, "qa_set.json"), encoding="utf-8"))
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL,
                                                 dtype=torch.float32).eval()

    def prompt(q):
        msgs = [{"role": "user",
                 "content": f"Answer in a few words. {q}"}]
        try:
            return tok.apply_chat_template(msgs, tokenize=False,
                                           add_generation_prompt=True)
        except Exception:
            return f"Question: {q}\nAnswer:"

    rows = []
    for i, item in enumerate(qa):
        p = prompt(item["q"])
        enc = tok(p, return_tensors="pt")
        plen = enc.input_ids.shape[1]
        with torch.no_grad():
            g = model.generate(**enc, max_new_tokens=32, do_sample=False,
                               return_dict_in_generate=True,
                               output_scores=True)
        gen_ids = g.sequences[0][plen:]
        probs = [float(torch.softmax(s, dim=-1)[0, t])
                 for s, t in zip(g.scores, gen_ids)]
        greedy = tok.decode(gen_ids, skip_special_tokens=True)
        samples = []
        with torch.no_grad():
            for _ in range(N_SAMPLES):
                s = model.generate(**enc, max_new_tokens=32, do_sample=True,
                                   temperature=0.7, top_p=0.9)
                samples.append(tok.decode(s[0][plen:],
                                          skip_special_tokens=True))
        votes = [norm(greedy)] + [norm(x) for x in samples]
        top = max(set(votes), key=votes.count)
        disagree = 1.0 - votes.count(top) / len(votes)
        # Input-side familiarity: mean logprob of the PROMPT tokens under
        # the model (teacher-forced, one forward pass, no generation).
        # This is the closest black-box analog of ROX S_t: how surprising
        # is the *input*, as opposed to how uncertain is the *output*.
        with torch.no_grad():
            logits = model(**enc).logits[0]
        logp = torch.log_softmax(logits, dim=-1)
        toks = enc.input_ids[0]
        qlp = [float(logp[i, toks[i + 1]]) for i in range(plen - 1)]
        rows.append({
            "q": item["q"], "gold": item["a"], "out": greedy,
            "correct": correct(greedy, item["a"]),
            "min_prob": min(probs) if probs else 0.0,
            "mean_logprob": sum(math.log(max(p, 1e-12)) for p in probs)
            / max(1, len(probs)),
            "disagree": disagree,
            "q_fam": sum(qlp) / max(1, len(qlp)),
            "samples": samples,
        })
        print(f"[{i + 1}/{len(qa)}] {'OK ' if rows[-1]['correct'] else 'WRONG'} "
              f"minp={rows[-1]['min_prob']:.3f} dis={disagree:.2f} "
              f"q={item['q'][:44]} -> {greedy[:40]!r}",
              flush=True)
    acc = sum(r["correct"] for r in rows) / len(rows)
    out = {"model": MODEL, "accuracy": acc, "rows": rows}
    json.dump(out, open(os.path.join(HERE, "results.json"), "w"),
              indent=1)
    print(f"[measure] accuracy={acc:.2f} wrote results.json "
          f"({sum(not r['correct'] for r in rows)} wrong answers to detect)")


if __name__ == "__main__":
    sys.exit(main())
