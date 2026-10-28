"""ORPO (Odds Ratio Preference Optimization) — SFT + alignment in one loss.

No reference model. Fuses SFT and preference optimization:
  loss = BCE(logit, label) + lambda * odds_ratio(chosen, rejected)

Uses ALL UltraFeedback pairs.  python run_orpo.py [--steps N]
"""
import json
import os
import sys
import time

import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hf_backend import HFDraft, norm  # noqa: E402

MODEL = os.path.join(HERE, "rox_brain")
OUT = os.path.join(HERE, "rox_orpo")
PREFS_FILE = os.path.join(HERE, "dpo_prefs.jsonl")
PERSONA_FILE = os.path.join(HERE, "persona_prefs.json")
LAMBDA = 0.1
LR = 5e-6
STEPS = 100


def load_data():
    rows = []
    with open(PREFS_FILE, encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    for d in json.load(open(PERSONA_FILE, encoding="utf-8")):
        for _ in range(10):
            rows.append(d)
    return rows


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


def run():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import lora as lora_mod

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16)
    model.config.use_cache = False
    lora_mod.attach(model)
    opt = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=LR)
    data = load_data()
    t0 = time.time()
    for s in range(STEPS):
        batch = [data[i] for i in torch.randint(0, len(data), (4,)).tolist()]
        opt.zero_grad()
        total_loss = 0.0
        for d in batch:
            chosen_ids = encode(tok, d["prompt"], d["chosen"])
            rejected_ids = encode(tok, d["prompt"], d["rejected"])
            lp_c = seq_logp(model, chosen_ids)
            lp_r = seq_logp(model, rejected_ids)
            # SFT loss on chosen (mask is implicit: full-seq logp)
            sft_loss = -lp_c
            # ORPO: odds ratio preference term
            odds_ratio = torch.exp(lp_c - lp_r)
            orpo_loss = -LAMBDA * torch.log(odds_ratio + 1e-8)
            total_loss = total_loss + sft_loss + orpo_loss
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(
            [p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step()
        print(f"[orpo] step {s + 1}/{STEPS} loss={float(total_loss):.3f} "
              f"({time.time() - t0:.0f}s)", flush=True)

    lora_mod.merge_all(model)
    lora_mod.strip_adapters(model)
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f"[orpo] saved {OUT}")


if __name__ == "__main__":
    run()
