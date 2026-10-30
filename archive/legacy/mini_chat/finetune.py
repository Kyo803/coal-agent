"""Fine-tune SmolLM2-135M-Instruct into 'Coal' (CPU-friendly).

Frozen base, train only the last 2 transformer blocks + LM head:
fast on CPU, keeps general language intact, teaches basics + Coal facts.
Loss is masked to assistant tokens only. Saves ./model/.
"""
import json
import os

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
OUT = os.path.join(HERE, "model")
EPOCHS = 2
LR = 1e-4
BATCH = 4
# User-side variants: same fact, different wrappings (robustness, not new info).
UVARIANTS = ["{u}"]  # variants off: tiny data + variants = memorised noise
# Minimal footprint: last block only, head frozen (least distortion).


def encode_pair(tok, user, asst):
    pre = tok.apply_chat_template(
        [{"role": "user", "content": user}], tokenize=False,
        add_generation_prompt=True)
    full = tok.apply_chat_template(
        [{"role": "user", "content": user},
         {"role": "assistant", "content": asst}],
        tokenize=False, add_generation_prompt=False) + tok.eos_token
    pre_ids = tok(pre, add_special_tokens=False).input_ids
    full_ids = tok(full, add_special_tokens=False).input_ids
    labels = [-100] * len(pre_ids) + full_ids[len(pre_ids):]
    return full_ids, labels


def main():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    data = json.load(open(os.path.join(HERE, "dataset.json"),
                          encoding="utf-8"))
    train = [d for d in data if d["split"] == "train"]
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL,
                                                 dtype=torch.float32)
    # Freeze everything except last 2 blocks + head.
    for p in model.parameters():
        p.requires_grad = False
    for layer in model.model.layers[-1:]:
        for p in layer.parameters():
            p.requires_grad = True
    ntrain = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[finetune] trainable={ntrain / 1e6:.1f}M / "
          f"{sum(p.numel() for p in model.parameters()) / 1e6:.0f}M")

    batch = []
    for d in train:
        for v in UVARIANTS:
            batch.append([torch.tensor(x) for x in encode_pair(
                tok, v.format(u=d["user"]), d["assistant"])])
    opt = torch.optim.AdamW([p for p in model.parameters()
                             if p.requires_grad], lr=LR)
    model.train()
    for ep in range(EPOCHS):
        tot = 0.0
        for i in range(0, len(batch), BATCH):
            chunk = batch[i:i + BATCH]
            L = max(len(ids) for ids, _ in chunk)
            ids = torch.stack([torch.nn.functional.pad(
                x, (0, L - len(x)), value=tok.pad_token_id or 0)
                for x, _ in chunk])
            lab = torch.stack([torch.nn.functional.pad(
                torch.tensor(l), (0, L - len(l)), value=-100)
                for _, l in chunk])
            attn = (ids != (tok.pad_token_id or 0)).long()
            opt.zero_grad()
            loss = model(input_ids=ids, attention_mask=attn,
                         labels=lab).loss
            loss.backward()
            opt.step()
            tot += float(loss.detach())
        print(f"[finetune] epoch {ep}: loss={tot / (len(batch) / BATCH):.4f}",
              flush=True)
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f"[finetune] saved {OUT}")


if __name__ == "__main__":
    main()
