"""KTO (Kahneman-Tversky Optimization) — unpaired thumbs up/down.

No reference model needed. Each sample is independent:
  loss = -sigmoid(beta * log_ratio) * weight(desirable/undesirable)

Uses ALL 61K UltraFeedback pairs (not just matched subsets like DPO).
  python run_kto.py [--steps N]
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
OUT = os.path.join(HERE, "rox_kto")
PREFS_FILE = os.path.join(HERE, "dpo_prefs.jsonl")
PERSONA_FILE = os.path.join(HERE, "persona_prefs.json")
BETA = 0.5
LR = 5e-6
STEPS = 100
CKPT = os.path.join(HERE, "ckpt_kto.pt")


def load_data():
    rows = []
    with open(PREFS_FILE, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            rows.append(d)
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
    start = 1
    if os.path.exists(CKPT):
        ck = torch.load(CKPT, map_location="cpu", weights_only=False)
        for n, p in model.named_parameters():
            if n in ck["adapters"]:
                p.data.copy_(ck["adapters"][n])
        opt.load_state_dict(ck["opt"])
        start = ck["step"] + 1
        print(f"[kto] resumed from step {ck['step']}", flush=True)
    for s in range(start, STEPS + 1):
        batch = [data[i] for i in torch.randint(0, len(data), (4,)).tolist()]
        opt.zero_grad()
        total_loss = 0.0
        for d in batch:
            chosen_ids = encode(tok, d["prompt"], d["chosen"])
            rejected_ids = encode(tok, d["prompt"], d["rejected"])
            lp_c = seq_logp(model, chosen_ids)
            lp_r = seq_logp(model, rejected_ids)
            # KTO: upweight undesirable (rejected) samples
            w_des = 1.0
            w_undes = 2.0  # penalty asymmetry
            loss_des = -F.logsigmoid(BETA * lp_c) * w_des
            loss_undes = -F.logsigmoid(-BETA * lp_r) * w_undes
            total_loss = total_loss + loss_des + loss_undes
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(
            [p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step()
        if s % 25 == 0:
            torch.save({"step": s,
                        "adapters": {n: p.detach().cpu().clone()
                                     for n, p in model.named_parameters()
                                     if p.requires_grad},
                        "opt": opt.state_dict()}, CKPT)
        print(f"[kto] step {s + 1}/{STEPS} loss={float(total_loss):.3f} "
              f"({time.time() - t0:.0f}s)", flush=True)

    lora_mod.merge_all(model)
    lora_mod.strip_adapters(model)
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f"[kto] saved {OUT}")


if __name__ == "__main__":
    run()
