"""DPO alignment on prefs + persona set. Policy = rox_brain + fresh LoRA;
reference = frozen rox_brain copy. Masked completion log-probs, beta 0.1.
Saves merged rox_chat/.  python train_dpo.py [--steps N]
"""
import json
import os
import sys
import time

import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "rox_brain")
OUT = os.path.join(HERE, "rox_chat")
PREFS = os.path.join(HERE, "dpo_prefs.jsonl")
PERSONA = os.path.join(HERE, "persona_prefs.json")
STEPS, BATCH, BETA, LR = 300, 1, 0.05, 3e-5
CKPT_EVERY = 25
CKPT = os.path.join(HERE, "ckpt_dpo.pt")


def encode(tok, prompt, completion, ctx=256):
    pre = tok.apply_chat_template(
        [{"role": "user", "content": prompt}], tokenize=False,
        add_generation_prompt=True)
    full = tok.apply_chat_template(
        [{"role": "user", "content": prompt},
         {"role": "assistant", "content": completion}],
        tokenize=False, add_generation_prompt=False) + tok.eos_token
    pre_ids = tok(pre, add_special_tokens=False).input_ids
    full_ids = tok(full, add_special_tokens=False).input_ids
    if len(full_ids) > ctx:
        full_ids = full_ids[-ctx:]
        pre_ids = pre_ids[-(ctx - 8):]
    mask = [False] * min(len(pre_ids), len(full_ids)) \
        + [True] * max(0, len(full_ids) - len(pre_ids))
    return full_ids, mask


def load_data(tok, limit_prefs=40000):
    # Raw triples only — tokenized per batch in the loop (upfront
    # tokenizing 40K pairs hangs the start for an hour).
    rows = []
    with open(PREFS, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit_prefs:
                break
            d = json.loads(line)
            if d.get("prompt") and d.get("chosen") and d.get("rejected"):
                rows.append(d)
    persona = json.load(open(PERSONA, encoding="utf-8"))
    return rows, persona


def prep(tok, d):
    try:
        return (encode(tok, d["prompt"], d["chosen"]),
                encode(tok, d["prompt"], d["rejected"]))
    except Exception:
        return None


def pad_batch(items, tok, pad=None):
    pad = tok.pad_token_id if tok.pad_token_id is not None else 0
    L = max(len(x[0]) for x in items)
    out = []
    for ids, mask in items:
        out.append((torch.nn.functional.pad(torch.tensor(ids),
                                            (0, L - len(ids)), value=pad),
                    torch.nn.functional.pad(torch.tensor(mask),
                                            (0, L - len(mask)),
                                            value=False)))
    batch_ids = torch.stack([x[0] for x in out])
    batch_mask = torch.stack([x[1] for x in out])
    return batch_ids, batch_mask, (batch_ids != pad).long()


def seq_logp(model, ids, mask, attn):
    out = model(input_ids=ids[:, :-1], attention_mask=attn[:, :-1])
    lp = F.log_softmax(out.logits.float(), -1)
    m = mask[:, 1:]
    t = ids[:, 1:]
    return (lp.gather(-1, t.unsqueeze(-1)).squeeze(-1) * m).sum(-1) \
        / m.sum(-1).clamp(min=1)


def main():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import lora as lora_mod
    import copy
    steps = STEPS
    for a in sys.argv[1:]:
        if a.startswith("--steps="):
            steps = int(a.split("=", 1)[1])
    dt = torch.bfloat16
    tok = AutoTokenizer.from_pretrained(BASE)
    prefs, persona = load_data(tok)
    print(f"[dpo] prefs={len(prefs)} persona={len(persona)}", flush=True)
    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=dt)
    model.config.use_cache = False
    lora_mod.attach(model)
    ref = copy.deepcopy(model)
    for p in ref.parameters():
        p.requires_grad = False
    ref.eval()
    opt = torch.optim.AdamW([p for p in model.parameters()
                             if p.requires_grad], lr=LR)
    import random
    rng = random.Random(1)

    def draw():
        # ~15% persona slots: alignment must stick without drowning prefs.
        d = rng.choice(persona) if rng.random() < 0.15 \
            else prefs[rng.randrange(len(prefs))]
        return prep(tok, d)

    start = 1
    if os.path.exists(CKPT):
        ck = torch.load(CKPT, map_location="cpu", weights_only=False)
        for name, p in model.named_parameters():
            if name in ck["adapters"]:
                p.data.copy_(ck["adapters"][name])
        opt.load_state_dict(ck["opt"])
        rng.setstate(ck["rng"])
        start = ck["step"] + 1
        print(f"[dpo] resumed from step {ck['step']}", flush=True)
    t0 = time.time()
    for s in range(start, steps + 1):
        batch = [x for x in (draw(), draw()) if x is not None]
        if not batch:
            continue
        cs = pad_batch([b[0] for b in batch], tok)
        rs = pad_batch([b[1] for b in batch], tok)
        opt.zero_grad()
        with torch.no_grad():
            rf_c = seq_logp(ref, *cs)
            rf_r = seq_logp(ref, *rs)
        lp_c = seq_logp(model, *cs)
        lp_r = seq_logp(model, *rs)
        margin = (lp_c - rf_c) - (lp_r - rf_r)
        loss = -F.logsigmoid(BETA * margin).mean()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(
            [p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step()
        if s % CKPT_EVERY == 0:
            torch.save({"step": s,
                        "adapters": {n: p.detach().cpu().clone()
                                     for n, p in model.named_parameters()
                                     if p.requires_grad},
                        "opt": opt.state_dict(),
                        "rng": rng.getstate()}, CKPT)
        if s % 25 == 0 or s == 1:
            print(f"[dpo] step {s}/{steps} loss={float(loss.detach()):.3f} "
                  f"margin={float(margin.mean().detach()):.3f} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    lora_mod.merge_all(model)
    lora_mod.strip_adapters(model)
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f"[dpo] saved {OUT}")


if __name__ == "__main__":
    main()
