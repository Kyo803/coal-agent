"""Self-distillation save-point: SFT on own best rollouts.

Periodically: model generates N completions, rank by rule-based quality,
SFT on top-K. Keeps training alive when DPO/GRPO plateau.
  python run_distill.py [--steps N]
"""
import json
import os
import re
import sys
import time

import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

QA = json.load(open(os.path.join(os.path.dirname(HERE), "str_trigger",
                                 "qa_set.json"), encoding="utf-8"))
MODEL = os.path.join(HERE, "rox_brain")
OUT = os.path.join(HERE, "rox_distill")
STEPS = 200
LR = 2e-5


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def quality(out, gold):
    """Rule-based quality: correctness + brevity + no repetition."""
    o, g = norm(out), norm(gold)
    correct = 1.0 if g and o and (g in o or o in g) else 0.0
    brevity = min(1.0, 50.0 / max(len(out), 1))
    unique = len(set(out.split())) / max(1, len(out.split()))
    return correct * 0.6 + brevity * 0.2 + unique * 0.2


def encode_pair(tok, prompt, response, max_len=200):
    pre = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                  tokenize=False, add_generation_prompt=True)
    full = pre + response + tok.eos_token
    ids = tok(full, return_tensors="pt").input_ids
    if ids.shape[1] > max_len:
        ids = ids[:, -max_len:]
    pre_len = len(tok(pre, add_special_tokens=False).input_ids)
    labels = torch.full_like(ids, -100)
    labels[pre_len:] = ids[pre_len:]
    return ids.squeeze(0), labels.squeeze(0)


def generate_completions(model, tok, n=4):
    """Model generates N completions per question, rank by quality."""
    completions = []
    for item in QA:
        prompt = tok.apply_chat_template(
            [{"role": "user", "content": item["q"]}],
            tokenize=False, add_generation_prompt=True)
        samples = []
        for _ in range(n):
            enc = tok(prompt, return_tensors="pt")
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=48, do_sample=True,
                                     temperature=0.8, top_p=0.9)
            resp = tok.decode(out[0][enc.input_ids.shape[1]:],
                              skip_special_tokens=True)
            q = quality(resp, item["a"])
            samples.append((resp, q))
        # Take top-K by quality (K=2 per question)
        samples.sort(key=lambda x: -x[1])
        for resp, _ in samples[:2]:
            completions.append({"prompt": item["q"], "response": resp})
    return completions


def run():
    import re
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import lora as lora_mod

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16)
    model.config.use_cache = False
    lora_mod.attach(model)
    opt = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=LR)
    t0 = time.time()
    for s in range(STEPS):
        # Phase 1: generate self-distillation data (every 20 steps)
        if s % 20 == 0:
            data = generate_completions(model, tok, n=4)
        batch_idx = torch.randint(0, len(data), (2,)).tolist()
        batch = [data[i] for i in batch_idx]

        opt.zero_grad()
        total_loss = 0.0
        for d in batch:
            ids, labels = encode_pair(tok, d["prompt"], d["response"])
            out = model(input_ids=ids.unsqueeze(0))
            shift_logits = out.logits[0, :-1]
            shift_labels = labels[1:]
            mask = shift_labels != -100
            loss = F.cross_entropy(
                shift_logits[mask], shift_labels[mask]) if mask.any() else torch.tensor(0.0)
            total_loss = total_loss + loss
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(
            [p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step()
        if s % 10 == 0:
            print(f"[distill] step {s + 1}/{STEPS} loss={float(total_loss):.3f} "
                  f"data_size={len(data)} ({time.time() - t0:.0f}s)", flush=True)

    lora_mod.merge_all(model)
    lora_mod.strip_adapters(model)
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f"[distill] saved {OUT}")


if __name__ == "__main__":
    run()
