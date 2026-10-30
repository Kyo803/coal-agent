"""SFT v2: instruction + conversation + memory-tools + safety + code.

Masked loss on assistant tokens. Muon+AdamW. Resumable.
  python sft_v2.py --smoke                 # CPU smoke
  torchrun --nproc_per_node=10 sft_v2.py --tier 500M --base ckpt_v2/v2.pt

Data sources (mix from config_v2.SFTDataMix):
  instruction : D:/coal_data/instr + existing sft pairs
  conversation: D:/coal_data/fresh
  memory_tools: generated here (teaches search/remember tool calls)
  safety      : D:/coal_data/safety/safety_sft.jsonl
  code_guidance: D:/coal_data/code (templated)
"""
import argparse
import glob
import json
import os
import random
import sys

import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from arch_v2 import CoalChatV2, CFG_TINY_V2  # noqa: E402
from config_v2 import TIERS, SFTDataMix  # noqa: E402
from muon import HybridMuon  # noqa: E402

# memory-tool SFT examples: teach WHEN to call tools
MEMORY_TOOL_SFT = [
    {"messages": [
        {"role": "user", "content": "what is my dog's name?"},
        {"role": "assistant",
         "content": "<|tools|>search_memory: dog name<|tools|>"}]},
    {"messages": [
        {"role": "user", "content": "remind me what motors my robot arm "
                                    "uses"},
        {"role": "assistant",
         "content": "<|tools|>search_memory: robot arm motors<|tools|>"}]},
    {"messages": [
        {"role": "user", "content": "remember that my project uses CAN bus"},
        {"role": "assistant",
         "content": "<|tools|>remember: project uses CAN bus<|tools|>"}]},
    {"messages": [
        {"role": "user", "content": "call me by my preferred name from now"},
        {"role": "assistant",
         "content": "<|tools|>update_profile: style=first-name<|tools|>"}]},
    {"messages": [
        {"role": "user", "content": "forget my old address"},
        {"role": "assistant",
         "content": "<|tools|>forget: old address<|tools|>"}]},
]


def render(msgs):
    """Manual chat template matching the tokenizer's special tokens."""
    out = []
    for m in msgs:
        role = m["role"]
        if role == "system":
            out.append(f"<|system|>{m['content']}")
        elif role == "user":
            out.append(f"<|user|>{m['content']}")
        elif role == "assistant":
            out.append(f"<|assistant|>{m['content']}")
        else:
            out.append(m["content"])
    return "".join(out)


def encode(tok, msgs, max_len=1024):
    """Full text + assistant-only label mask (prompt tokens = -100)."""
    pre_msgs = [m for m in msgs if m["role"] != "assistant"]
    prompt = render(pre_msgs) + "<|assistant|>"
    full = render(msgs) + "<|endoftext|>"
    pre_ids = tok.encode(prompt).ids
    full_ids = tok.encode(full).ids
    if len(full_ids) > max_len:
        full_ids = full_ids[-max_len:]
        pre_ids = pre_ids[-(max_len - 16):]
    n = min(len(pre_ids), len(full_ids))
    labels = [-100] * n + full_ids[n:]
    return full_ids, labels


def load_sft(tok, max_len=1024, limit=60000):
    rows = []
    # memory-tools (repeat)
    for _ in range(200):
        for d in MEMORY_TOOL_SFT:
            rows.append(encode(tok, d["messages"], max_len))
    # instruction + safety + atp
    for pat in ("D:/coal_data/instr/*.jsonl",
                "D:/coal_data/safety/safety_sft.jsonl",
                "D:/coal_data/atp/atp_sft.jsonl",
                os.path.join(HERE, "sft_train.jsonl")):
        for fp in glob.glob(pat):
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    if len(rows) >= limit:
                        break
                    try:
                        d = json.loads(line)
                        msgs = d.get("messages")
                        if not msgs:
                            continue
                        rows.append(encode(tok, msgs, max_len))
                    except Exception:
                        continue
    return [r for r in rows if len(r[0]) > 8
            and any(l != -100 for l in r[1])]


def batchify(rows, tok, pad=0):
    L = max(len(r[0]) for r in rows)
    ids = torch.stack([F.pad(torch.tensor(r[0]), (0, L - len(r[0])),
                            value=pad) for r in rows])
    lab = torch.stack([F.pad(torch.tensor(r[1]), (0, L - len(r[1])),
                            value=-100) for r in rows])
    return ids, lab, (ids != pad).long()


def smoke():
    print("== sft_v2 smoke (CPU) ==")
    torch.manual_seed(0)
    m = CoalChatV2(CFG_TINY_V2)
    opt = HybridMuon(m, muon_lr=0.02, adamw_lr=3e-4)
    B, T = 2, 64
    cyc = torch.arange(T) % 16
    for s in range(1, 11):
        ids = cyc.repeat(B, 1)
        lab = ids.clone()
        lab[:, :16] = -100
        opt.zero_grad()
        logits, aux, _ = m(ids[:, :-1])
        l = lab[:, 1:]
        loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1])[l.reshape(-1) != -100],
                               ids[:, 1:].reshape(-1)[l.reshape(-1) != -100])
        loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
        opt.step()
        if s % 5 == 0:
            print(f"[sft] step {s}/10 loss={float(loss.detach()):.3f}")
    print("[sft] smoke OK")
    return 0


def train(args):
    from tokenizers import ByteLevelBPETokenizer
    tok = ByteLevelBPETokenizer(
        os.path.join(args.tokenizer, "vocab.json"),
        os.path.join(args.tokenizer, "merges.txt"))
    # patch tokenizer with chat template support via a shim
    rows = load_sft(tok, limit=args.limit)
    print(f"[sft] pairs={len(rows)}", flush=True)
    cfg = TIERS[args.tier]
    m = CoalChatV2(cfg)
    if args.base and os.path.exists(args.base):
        ck = torch.load(args.base, map_location="cpu", weights_only=False)
        sd = m.state_dict()
        for k, v in ck["model"].items():
            if k in sd:
                sd[k] = v.to(sd[k].dtype)
        m.load_state_dict(sd)
        print(f"[sft] loaded base {args.base}")
    opt = HybridMuon(m, muon_lr=0.01, adamw_lr=1e-4)
    rng = random.Random(0)
    for s in range(1, args.steps + 1):
        batch = [rows[i] for i in rng.sample(range(len(rows)), args.batch)]
        ids, lab, attn = batchify(batch, tok)
        opt.zero_grad()
        logits, aux, _ = m(ids[:, :-1])
        l = lab[:, 1:]
        tgt = ids[:, 1:]
        mask = l.reshape(-1) != -100
        loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1])[mask],
                               tgt.reshape(-1)[mask])
        loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
        opt.step()
        if s % 25 == 0 or s == 1:
            print(f"[sft] step {s}/{args.steps} loss={float(loss.detach()):.3f}",
                  flush=True)
            torch.save({"model": m.state_dict(),
                        "config": cfg.__dict__},
                       os.path.join(args.ckpt, "sft_v2.pt"))
    print(f"[sft] done -> {args.ckpt}/sft_v2.pt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--tier", default="500M", choices=list(TIERS))
    ap.add_argument("--base", default=None)
    ap.add_argument("--tokenizer", default=os.path.join(HERE, "tokenizer_v2"))
    ap.add_argument("--ckpt", default=os.path.join(HERE, "ckpt_v2"))
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--limit", type=int, default=60000)
    args = ap.parse_args()
    if args.smoke:
        sys.exit(smoke())
    os.makedirs(args.ckpt, exist_ok=True)
    train(args)


if __name__ == "__main__":
    main()
