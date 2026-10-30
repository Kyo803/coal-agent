"""Before/after test: grade held-out basics with BASE vs FINETUNED model."""
import json
import os
import re

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def ok(out, gold):
    o, g = norm(out), norm(gold)
    return bool(o) and bool(g) and (g in o or o in g)


def run(model, tok, held):
    model.eval()
    score = []
    with torch.no_grad():
        for d in held:
            p = tok.apply_chat_template(
                [{"role": "user", "content": d["user"]}], tokenize=False,
                add_generation_prompt=True)
            enc = tok(p, return_tensors="pt")
            n = enc.input_ids.shape[1]
            out = model.generate(**enc, max_new_tokens=40, do_sample=False)
            txt = tok.decode(out[0][n:], skip_special_tokens=True)
            hit = ok(txt, d["assistant"])
            score.append(hit)
            print(f"  [{'OK ' if hit else 'MISS'}] {d['user'][:40]:42s} -> "
                  f"{txt[:50]!r} (want {d['assistant'][:30]!r})")
    return sum(score) / len(score)


def main():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    data = json.load(open(os.path.join(HERE, "dataset.json"),
                          encoding="utf-8"))
    held = [d for d in data if d["split"] == "heldout"]
    res = {}
    for name, src in (("base", BASE), ("finetuned", os.path.join(HERE, "model"))):
        tok = AutoTokenizer.from_pretrained(src)
        model = AutoModelForCausalLM.from_pretrained(src, dtype=torch.float32)
        print(f"--- {name} ---")
        res[name] = run(model, tok, held)
    print(f"\n[eval] base={res['base']:.2f} finetuned={res['finetuned']:.2f}")
    json.dump(res, open(os.path.join(HERE, "eval.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
