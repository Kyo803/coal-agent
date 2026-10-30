"""Online Iterative DPO: generate → rank → train → repeat.

Each round:
  1. Model generates 4 completions per question
  2. Rule-based scoring ranks them
  3. Top vs bottom become chosen/rejected pairs
  4. DPO loss with old ref logprobs

Combines generation fresh data (fixes stale prefs) with DPO structure.
  python run_online_dpo.py [--rounds N]
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
MODEL = os.path.join(HERE, "coal_brain")
OUT = os.path.join(HERE, "coal_online_dpo")
ROUNDS = 3
STEPS_PER_ROUND = 50
BETA = 0.1
LR = 5e-6
G = 4


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def reward(out, gold):
    o, g = norm(out), norm(gold)
    correct = 1.0 if g and o and (g in o or o in g) else 0.0
    brevity = min(1.0, 50.0 / max(len(out), 1))
    unique = len(set(out.split())) / max(1, len(out.split()))
    return correct * 0.6 + brevity * 0.2 + unique * 0.2


def encode(tok, prompt, text, max_len=200):
    msgs = [{"role": "user", "content": prompt},
             {"role": "assistant", "content": text}]
    try:
        full = tok.apply_chat_template(msgs, tokenize=False,
                                       add_generation_prompt=False) + tok.eos_token
    except Exception:
        full = f"User: {prompt}\nAssistant: {text}{tok.eos_token}"
    ids = tok(full, return_tensors="pt").input_ids
    if ids.shape[1] > max_len:
        ids = ids[:, -max_len:]
    return ids.squeeze(0)


def seq_logp(model, ids):
    out = model(input_ids=ids.unsqueeze(0))
    lp = F.log_softmax(out.logits.float(), -1)
    return lp[0, :-1].gather(1, ids[1:].unsqueeze(1)).squeeze(-1).mean()


def generate_and_rank(model, tok):
    """Generate G responses per question, return top/bottom as pairs."""
    pairs = []
    for item in QA:
        prompt = tok.apply_chat_template(
            [{"role": "user", "content": item["q"]}],
            tokenize=False, add_generation_prompt=True)
        samples = []
        for _ in range(G):
            enc = tok(prompt, return_tensors="pt")
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=48, do_sample=True,
                                     temperature=0.7, top_p=0.9)
            resp = tok.decode(out[0][enc.input_ids.shape[1]:],
                              skip_special_tokens=True)
            q = reward(resp, item["a"])
            samples.append((resp, q))
        samples.sort(key=lambda x: -x[1])
        if samples[0][1] > samples[-1][1]:  # only train on meaningful pairs
            pairs.append({
                "prompt": item["q"],
                "chosen": samples[0][0],
                "rejected": samples[-1][0]
            })
    return pairs


def run():
    import copy
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import lora as lora_mod

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16)
    model.config.use_cache = False
    lora_mod.attach(model)
    ref = copy.deepcopy(model)
    for p in ref.parameters():
        p.requires_grad = False
    ref.eval()
    opt = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=LR)
    t0 = time.time()

    for rnd in range(ROUNDS):
        print(f"\n=== ROUND {rnd + 1}/{ROUNDS} ===", flush=True)
        # Generate fresh preferences from current model
        pairs = generate_and_rank(model, tok)
        print(f"[online_dpo] round {rnd + 1}: {len(pairs)} pairs", flush=True)

        # DPO on fresh pairs
        for s in range(STEPS_PER_ROUND):
            batch = [pairs[i] for i in
                     torch.randint(0, len(pairs), (2,)).tolist()]
            opt.zero_grad()
            total_loss = 0.0
            for d in batch:
                chosen_ids = encode(tok, d["prompt"], d["chosen"])
                rejected_ids = encode(tok, d["prompt"], d["rejected"])
                lp_c = seq_logp(model, chosen_ids)
                lp_r = seq_logp(model, rejected_ids)
                rl_c = seq_logp(ref, chosen_ids)
                rl_r = seq_logp(ref, rejected_ids)
                margin = (lp_c - rl_c) - (lp_r - rl_r)
                loss = -F.logsigmoid(BETA * margin).mean()
                total_loss = total_loss + loss
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0)
            opt.step()
            if s % 10 == 0:
                print(f"  step {s + 1}/{STEPS_PER_ROUND} "
                      f"loss={float(total_loss):.3f}", flush=True)

    lora_mod.merge_all(model)
    lora_mod.strip_adapters(model)
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f"[online_dpo] saved {OUT}")


if __name__ == "__main__":
    run()
