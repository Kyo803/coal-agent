"""500M from-scratch pretrain + SFT + alignment on CPU (resumable).

Usage:
  python train_500m.py --mode pretrain --steps 500
  python train_500m.py --mode sft      --steps 200
  python train_500m.py --mode align    --steps 200
  python train_500m.py --mode eval     (test checkpoint)
All modes save to rox_500m/ with 25-step checkpoints and resume.
"""
import argparse
import json
import os
import sys
import time

import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from arch import RoxChat, CFG_500M_BYTE  # noqa: E402

OUT = os.path.join(HERE, "rox_500m")
CKPT_PRE = os.path.join(OUT, "pretrain.pt")
CKPT_SFT = os.path.join(OUT, "sft.pt")
CKPT_ALN = os.path.join(OUT, "align.pt")
DT = torch.float32  # fp32: 1.9GB weights + ~4GB optim = ~6GB, fits 12GB
CTX = 512
BATCH = 1  # batch 1 for RAM safety on CPU
LR = 3e-4


def make_model():
    m = RoxChat(CFG_500M_BYTE)
    return m  # fp32, all layers stay float


def load_checkpoint(path, model, opt=None, rng=None):
    if not os.path.exists(path):
        return 0, None, None
    ck = torch.load(path, map_location="cpu", weights_only=False)
    sd = model.state_dict()
    for k, v in ck["model"].items():
        if k in sd:
            sd[k] = v.to(sd[k].dtype)
    model.load_state_dict(sd)
    if opt and "opt" in ck:
        try:
            opt.load_state_dict(ck["opt"])
        except Exception:
            pass
    if rng and "rng" in ck:
        rng.setstate(ck["rng"])
    return ck.get("step", 0), ck.get("val_loss", None), ck


def save_checkpoint(path, step, model, opt=None, rng=None, val_loss=None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sd = model.state_dict()
    ck = {"step": step, "model": {k: v.cpu() for k, v in sd.items()},
          "val_loss": val_loss}
    if opt:
        try:
            ck["opt"] = opt.state_dict()
        except Exception:
            pass
    if rng:
        ck["rng"] = rng.getstate()
    torch.save(ck, path)


@torch.no_grad()
def val_ppl(model, data, ctx=CTX, n=30):
    model.eval()
    tot, cnt = 0.0, 0
    for i in range(n):
        idx = torch.randint(0, len(data) - ctx - 1, (1,))
        x = data[idx:idx + ctx].unsqueeze(0)
        y = data[idx + 1:idx + ctx + 1].unsqueeze(0)
        logits, _, _ = model(x)
        loss = F.cross_entropy(logits.view(-1, logits.shape[-1]), y.view(-1))
        tot += float(loss) * ctx
        cnt += ctx
    model.train()
    return tot / max(1, cnt)


def pretrain(model, data, steps, start=0, ckpt_every=25):
    import random
    rng = random.Random(42)
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=LR, betas=(0.9, 0.95),
                            weight_decay=0.1)
    if start > 0:
        load_checkpoint(CKPT_PRE, model, opt)
    t0 = time.time()
    for s in range(start + 1, steps + 1):
        idx = torch.randint(0, len(data) - CTX - 1, (BATCH,))
        x = torch.stack([data[i:i + CTX] for i in idx])
        y = torch.stack([data[i + 1:i + CTX + 1] for i in idx])
        opt.zero_grad()
        logits, _, _ = model(x)
        loss = F.cross_entropy(
            logits.view(BATCH * CTX, -1), y.view(-1))
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if s % ckpt_every == 0 or s == 1:
            vl = val_ppl(model, data)
            save_checkpoint(CKPT_PRE, s, model, opt,
                           val_loss=vl)
            print(f"[pretrain] step {s}/{steps} loss={float(loss.detach()):.3f} "
                  f"val={vl:.3f} ({time.time() - t0:.0f}s)", flush=True)
    save_checkpoint(CKPT_PRE, steps, model, opt,
                   val_loss=val_ppl(model, data))
    print(f"[pretrain] done -> {CKPT_PRE}")


def sft(model, pairs, steps, start=0, ckpt_every=25):
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4, betas=(0.9, 0.95),
                            weight_decay=0.01)
    if start > 0:
        load_checkpoint(CKPT_SFT, model, opt)
    t0 = time.time()
    for s in range(start + 1, steps + 1):
        idx = torch.randint(0, len(pairs), (1,))
        ids, lab = pairs[idx[0]]
        ids, lab = ids.unsqueeze(0), lab.unsqueeze(0)
        opt.zero_grad()
        logits, _, _ = model(ids[:, :-1])
        loss = F.cross_entropy(
            logits.reshape(-1, 256)[lab[:, 1:].reshape(-1) != -100],
            ids[:, 1:][lab[:, 1:] != -100])
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if s % ckpt_every == 0 or s == 1:
            save_checkpoint(CKPT_SFT, s, model, opt)
            print(f"[sft] step {s}/{steps} loss={float(loss.detach()):.3f} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    save_checkpoint(CKPT_SFT, steps, model, opt)
    print(f"[sft] done -> {CKPT_SFT}")


def align_kto(model, prefs, steps, start=0, ckpt_every=25):
    """KTO on UltraFeedback pairs (unpaired thumbs up/down)."""
    import copy
    model.train()
    ref = copy.deepcopy(model)
    for p in ref.parameters():
        p.requires_grad = False
    ref.eval()
    opt = torch.optim.AdamW(model.parameters(), lr=5e-6, betas=(0.9, 0.95))
    if start > 0:
        load_checkpoint(CKPT_ALN, model, opt)
    t0 = time.time()
    for s in range(start + 1, steps + 1):
        idx = torch.randint(0, len(prefs), (2,))
        opt.zero_grad()
        total_loss = torch.tensor(0.0)
        for i in idx:
            c_ids = prefs[i][0]
            r_ids = prefs[i][1]
            with torch.no_grad():
                rl_c, _, _ = ref(c_ids.unsqueeze(0))
                rl_r, _, _ = ref(r_ids.unsqueeze(0))
            lp_c, _, _ = model(c_ids.unsqueeze(0))
            lp_r, _, _ = model(r_ids.unsqueeze(0))
            # KTO: chosen gets positive signal, rejected gets negative
            lpc = (lp_c[0, :-1].gather(1, c_ids[1:].unsqueeze(1)).squeeze(-1).mean())
            lpr = (lp_r[0, :-1].gather(1, r_ids[1:].unsqueeze(1)).squeeze(-1).mean())
            loss = -F.logsigmoid(0.5 * lpc) - 0.5 * F.logsigmoid(-0.5 * lpr)
            total_loss = total_loss + loss
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if s % ckpt_every == 0 or s == 1:
            save_checkpoint(CKPT_ALN, s, model, opt)
            print(f"[kto] step {s}/{steps} loss={float(total_loss):.3f} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    save_checkpoint(CKPT_ALN, steps, model, opt)
    print(f"[kto] done -> {CKPT_ALN}")


def test_checkpoint(model, path):
    if not os.path.exists(path):
        print(f"checkpoint {path} not found")
        return
    load_checkpoint(path, model)
    model.eval()
    print(f"\n--- Testing {path} ---")
    prompts = [
        "What is the capital of France?",
        "What is 2 plus 3?",
        "Tell me about ROX N",
        "Who are you?",
    ]
    for p in prompts:
        ids = encode(p)
        with torch.no_grad():
            out = model(ids.unsqueeze(0))
            next_tok = out[0, -1].argmax()
            resp = decode([next_tok.item()])
            # generate a few tokens
            full = list(ids) + [next_tok.item()]
            for _ in range(20):
                x = torch.tensor([full[-CTX:]])
                logits, _, _ = model(x)
                nxt = logits[0, -1].argmax().item()
                if nxt == 1:  # <eos>
                    break
                full.append(nxt)
            resp = decode(full[len(ids):])
        print(f"  Q: {p}")
        print(f"  A: {resp[:120]}")
        print()


def encode(s):
    return torch.tensor(list(s.encode("utf-8", errors="ignore")),
                        dtype=torch.long)[:CTX]


def decode(ids):
    return bytes([b for b in ids if 0 <= b < 256]).decode(
        "utf-8", errors="ignore")


def load_data():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "from_scratch"))
    from data_tinystories import load
    train, _ = load()
    return train


def load_sft_pairs():
    """Load dialogue pairs for SFT (message format -> token sequences)."""
    import json
    pairs = []
    for fp in ["sft_train.jsonl"]:
        path = os.path.join(HERE, fp)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                msgs = d.get("messages", [])
                if len(msgs) < 2:
                    continue
                user = next((m["content"] for m in msgs
                            if m["role"] == "user"), "")
                asst = next((m["content"] for m in msgs
                            if m["role"] == "assistant"), "")
                if not user or not asst:
                    continue
                # Format as byte sequence: <|user|>text<|asst|>text<|eos|>
                prompt = b"<|user|>" + user.encode("utf-8", errors="ignore")
                completion = b"<|asst|>" + asst.encode("utf-8", errors="ignore") + b"\x01"
                full = (prompt + completion)[-CTX:]
                pre_len = len(prompt) - (len(prompt + completion) - len(full))
                ids = torch.tensor(list(full), dtype=torch.long)
                labels = torch.full_like(ids, -100)
                labels[max(0, pre_len):] = ids[max(0, pre_len):]
                pairs.append((ids, labels))
    return pairs


def load_kto_pairs():
    """Load UltraFeedback pairs for KTO alignment."""
    path = os.path.join(HERE, "dpo_prefs.jsonl")
    if not os.path.exists(path):
        return []
    pairs = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 20000:
                break
            d = json.loads(line)
            c = b"<|asst|>" + d["chosen"].encode("utf-8", errors="ignore")[:400]
            r = b"<|asst|>" + d["rejected"].encode("utf-8", errors="ignore")[:400]
            c_ids = torch.tensor(list(c)[-CTX:], dtype=torch.long)
            r_ids = torch.tensor(list(r)[-CTX:], dtype=torch.long)
            pairs.append((c_ids, r_ids))
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pretrain", "sft", "align", "eval"])
    ap.add_argument("--steps", type=int, default=500)
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    m = make_model()
    print(f"500M model: {sum(p.numel() for p in m.parameters())/1e6:.1f}M params, "
          f"bf16={sum(p.nelement()*2 for p in m.parameters())/1e9:.1f}GB")

    if args.mode == "pretrain":
        data = load_data()
        # Resume logic
        start = 0
        if os.path.exists(CKPT_PRE):
            ck = torch.load(CKPT_PRE, map_location="cpu", weights_only=False)
            start = ck.get("step", 0)
            print(f"resuming pretrain from step {start}")
        pretrain(m, data, args.steps, start=start)

    elif args.mode == "sft":
        # Load pretrained
        if os.path.exists(CKPT_PRE):
            load_checkpoint(CKPT_PRE, m)
            print("loaded pretrained weights")
        pairs = load_sft_pairs()
        print(f"SFT pairs: {len(pairs)}")
        start = 0
        if os.path.exists(CKPT_SFT):
            ck = torch.load(CKPT_SFT, map_location="cpu", weights_only=False)
            start = ck.get("step", 0)
            print(f"resuming SFT from step {start}")
        sft(m, pairs, args.steps, start=start)

    elif args.mode == "align":
        if os.path.exists(CKPT_SFT):
            load_checkpoint(CKPT_SFT, m)
            print("loaded SFT weights")
        prefs = load_kto_pairs()
        print(f"KTO pairs: {len(prefs)}")
        start = 0
        if os.path.exists(CKPT_ALN):
            ck = torch.load(CKPT_ALN, map_location="cpu", weights_only=False)
            start = ck.get("step", 0)
            print(f"resuming KTO from step {start}")
        align_kto(m, prefs, args.steps, start=start)

    elif args.mode == "eval":
        test_checkpoint(m, CKPT_SFT)
        test_checkpoint(m, CKPT_ALN)


if __name__ == "__main__":
    main()
