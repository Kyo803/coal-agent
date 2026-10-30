"""GRPO (Group Relative Policy Optimization) — DeepSeek's method.

No reward model. No reference model. Just:
  1. Sample G responses per question
  2. Score each with rule-based rewards
  3. Advantage = (reward - group_mean) / group_std
  4. Policy gradient: maximize log_prob * advantage

Uses the 36 QA questions (real correctness signals) + UltraFeedback prompts.
LoRA on top of our SFT checkpoint.  python run_grpo.py [--steps N]
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
from hf_backend import HFDraft, norm  # noqa: E402

QA = json.load(open(os.path.join(os.path.dirname(HERE), "str_trigger",
                                 "qa_set.json"), encoding="utf-8"))
MODEL = os.path.join(HERE, "coal_brain")
OUT = os.path.join(HERE, "coal_grpo")
G = 4  # samples per question
BETA = 0.1
LR = 5e-6
STEPS = 100


def reward(out, gold):
    """Rule-based: 1 if gold substring in output, 0 otherwise."""
    o, g = norm(out), norm(gold)
    return 1.0 if g and o and (g in o or o in g) else 0.0


def log_prob(model, tok, prompt, response):
    pre = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                  tokenize=False, add_generation_prompt=True)
    full = pre + response + tok.eos_token
    ids = tok(full, return_tensors="pt").input_ids
    with torch.no_grad():
        logits = model(ids[:, :-1]).logits
    lp = F.log_softmax(logits.float(), -1).gather(-1, ids[:, 1:unsqueeze(0)])
    return float(lp.squeeze(-1).mean())


def generate_sample(model, tok, prompt, temp=0.7):
    enc = tok(prompt, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=48, do_sample=True,
                             temperature=temp, top_p=0.9)
    return tok.decode(out[0][enc.input_ids.shape[1]:],
                      skip_special_tokens=True)


def run():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import lora as lora_mod
    import copy

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
    for s in range(STEPS):
        # Sample G responses per question
        prompts = [item["q"] for item in QA]
        responses = []
        rewards = []
        old_lps = []
        for q in prompts:
            prompt = tok.apply_chat_template(
                [{"role": "user", "content": q}],
                tokenize=False, add_generation_prompt=True)
            gold = next((a for a in [next(
                (a2 for a2 in QA if a2["q"] == q), None
            ) if False else item["a"] for item in QA if item["q"] == q]),
                         QA[0]["a"])
            gold = next(item["a"] for item in QA if item["q"] == q)
            group_resps = []
            group_rews = []
            group_lps = []
            for _ in range(G):
                r = generate_sample(model, tok, prompt)
                rw = reward(r, gold)
                lp = log_prob(model, tok, prompt, r)
                rl = log_prob(ref, tok, prompt, r)
                group_resps.append(r)
                group_rews.append(rw)
                group_lps.append((lp, rl))
            # GRPO advantage: normalize within group
            mu = sum(group_rews) / G
            sigma = max(sum((r - mu) ** 2 for r in group_rews) / G, 1e-6) ** 0.5
            for j in range(G):
                a = (group_rews[j] - mu) / max(sigma, 1e-6)
                responses.append(group_resps[j])
                rewards.append(group_rews[j])
                old_lps.append(group_lps[j])

        # Policy gradient update
        opt.zero_grad()
        total_loss = 0.0
        for i, q in enumerate(prompts * G):
            prompt = tok.apply_chat_template(
                [{"role": "user", "content": q}],
                tokenize=False, add_generation_prompt=True)
            lp = log_prob(model, tok, prompt, responses[i])
            rl = old_lps[i][1]
            ratio = torch.exp(torch.tensor(lp - rl))
            adv = torch.tensor(rewards[i])
            # GRPO loss: policy gradient with KL penalty
            loss = -(ratio * adv).mean() + BETA * ratio.pow(2).mean()
            total_loss += loss
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(
            [p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step()
        mean_rew = sum(rewards) / len(rewards)
        print(f"[grpo] step {s + 1}/{STEPS} mean_reward={mean_rew:.3f} "
              f"loss={float(total_loss):.3f} ({time.time() - t0:.0f}s)",
              flush=True)

    lora_mod.merge_all(model)
    lora_mod.strip_adapters(model)
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f"[grpo] saved {OUT}")


if __name__ == "__main__":
    run()
