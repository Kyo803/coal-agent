"""SFT on OUR dialogue (sft_train.jsonl): LoRA q/v, assistant-masked loss.

  python train_sft.py [--steps N] [--batch N]
Logs train loss + val perplexity. Saves merged fp32 to rox_brain/.
CPU: ~10-20s/step @ batch 2 x seq 256 -> 300 steps ≈ 1h. Overnight-able.
"""
import json
import os
import sys
import time

import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
OUT = os.path.join(HERE, "rox_brain")
STEPS = 300
BATCH = 2
CTX = 256
LR = 5e-5  # low: the 2e-4 run memorized (loss 0.016 by step 100)
CKPT_EVERY = 25
CKPT = os.path.join(HERE, "ckpt_sft.pt")
DT = torch.bfloat16  # bf16 halves RAM (270MB weights); CPU-matmul verified


def encode_pair(tok, msgs):
    pre = tok.apply_chat_template(
        [m for m in msgs if m["role"] != "assistant"], tokenize=False,
        add_generation_prompt=True)
    full = tok.apply_chat_template(msgs, tokenize=False,
                                   add_generation_prompt=False) + tok.eos_token
    pre_ids = tok(pre, add_special_tokens=False).input_ids
    full_ids = tok(full, add_special_tokens=False).input_ids
    if len(full_ids) > CTX:
        full_ids = full_ids[-CTX:]
        pre_ids = pre_ids[-(CTX - 8):]
    labels = [-100] * min(len(pre_ids), len(full_ids)) \
        + full_ids[min(len(pre_ids), len(full_ids)):]
    return full_ids, labels


def load_pairs(path, tok, limit=None):
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            d = json.loads(line)
            try:
                ids, lab = encode_pair(tok, d["messages"])
            except Exception:
                continue
            if len(ids) < 16 or all(l == -100 for l in lab):
                continue
            rows.append((ids, lab))
    return rows


def batchify(rows, tok, pad=None):
    L = max(len(ids) for ids, _ in rows)
    pad = tok.pad_token_id if tok.pad_token_id is not None else 0
    ids = torch.stack([torch.nn.functional.pad(torch.tensor(x),
                                               (0, L - len(x)), value=pad)
                       for x, _ in rows])
    lab = torch.stack([torch.nn.functional.pad(torch.tensor(l),
                                               (0, L - len(l)), value=-100)
                       for _, l in rows])
    attn = (ids != pad).long()
    return ids, lab, attn


@torch.no_grad()
def val_ppl(model, val, tok):
    model.eval()
    tot, n = 0.0, 0
    for i in range(0, len(val), BATCH):
        ids, lab, attn = batchify(val[i:i + BATCH], tok)
        out = model(input_ids=ids[:, :-1],
                    attention_mask=attn[:, :-1] if attn is not None else None)
        l = lab[:, 1:]
        t = ids[:, 1:]
        loss = F.cross_entropy(out.logits[l != -100], t[l != -100])
        m = int((l != -100).sum())
        tot += float(loss) * m
        n += m
    model.train()
    return tot / max(1, n)


def main():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import lora as lora_mod
    steps, batch = STEPS, BATCH
    for a in sys.argv[1:]:
        if a.startswith("--steps="):
            steps = int(a.split("=", 1)[1])
        if a.startswith("--batch="):
            batch = int(a.split("=", 1)[1])
    tok = AutoTokenizer.from_pretrained(MODEL)
    train = load_pairs(os.path.join(HERE, "sft_train.jsonl"), tok)
    val = load_pairs(os.path.join(HERE, "sft_val.jsonl"), tok)[:150]
    print(f"[sft] train={len(train)} val={len(val)}", flush=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=DT, low_cpu_mem_usage=True)
    model.config.use_cache = False
    n_ad = lora_mod.attach(model)
    print(f"[sft] lora adapters={n_ad / 1e6:.2f}M trainable="
          f"{lora_mod.trainable_params(model) / 1e6:.2f}M", flush=True)
    opt = torch.optim.AdamW([p for p in model.parameters()
                             if p.requires_grad], lr=LR)
    import random
    rng = random.Random(0)
    start = 1
    if os.path.exists(CKPT):
        ck = torch.load(CKPT, map_location="cpu", weights_only=False)
        for name, p in model.named_parameters():
            if name in ck["adapters"]:
                p.data.copy_(ck["adapters"][name])
        opt.load_state_dict(ck["opt"])
        rng.setstate(ck["rng"])
        start = ck["step"] + 1
        print(f"[sft] resumed from step {ck['step']}", flush=True)
    p0 = val_ppl(model, val, tok)
    print(f"[sft] val_ppl before={p0:.3f}", flush=True)
    t0 = time.time()
    for s in range(start, steps + 1):
        rows = rng.sample(train, min(batch, len(train)))
        ids, lab, attn = batchify(rows, tok)
        opt.zero_grad()
        # NEXT-token objective: logits[i] predicts ids[i+1]. The previous
        # version omitted this shift (trained identity) and poisoned a
        # full 1000-step run — now explicitly shifted and tested.
        out = model(input_ids=ids[:, :-1], attention_mask=attn[:, :-1])
        l = lab[:, 1:]
        t = ids[:, 1:]
        loss = F.cross_entropy(out.logits[l != -100], t[l != -100])
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
        if s % 50 == 0 or s == 1:
            ppl = val_ppl(model, val, tok)
            print(f"[sft] step {s}/{steps} loss={float(loss.detach()):.3f} "
                  f"val_ppl={ppl:.3f} ({time.time() - t0:.0f}s)", flush=True)
    import lora as _lora_end
    _lora_end.merge_all(model)
    _lora_end.strip_adapters(model)
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f"[sft] saved merged {OUT}")


if __name__ == "__main__":
    main()
