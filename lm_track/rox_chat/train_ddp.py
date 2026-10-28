"""Rental entry: torchrun DDP/FSDP pretraining for RoxChat-500M on 60B.

  torchrun --nproc_per_node=10 train_ddp.py --tokens-b 60 --ckpt s3://.../
  CPU smoke: python train_ddp.py --smoke  (tiny cfg, 20 steps, no dist)

Design: plain full training, FIM stays OFFLINE (analysis only, never in
the hot loop — per spec). Sentinel parity probes + governor observe
hooks are optional flags (cheap, default on for probes every 2k steps).
FSDP FULL_SHARD on multi-GPU; single-proc falls back to plain AdamW.
Watchdog checkpoints every 5 min + tracks $ burn (rental_guardian).
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
from arch import RoxChat, Cfg, CFG_500M, CFG_TINY  # noqa: E402

CFG_500M_50K = Cfg(layers=18, d=960, heads=8, experts=8, moe_every=4,
                   vocab=50257, ctx=2048)


def get_model(cfg, dist):
    m = RoxChat(cfg)
    if dist and torch.cuda.device_count() > 1:
        from torch.distributed.fsdp import FullyShardedDataParallel as FSDP
        return FSDP(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens-b", type=float, default=60.0)
    ap.add_argument("--ckpt", default=os.path.join(HERE, "ckpt_500m"))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--batch-tokens", type=int, default=500000)
    ap.add_argument("--sentinel-every", type=int, default=2000)
    args = ap.parse_args()

    dist = "RANK" in os.environ and "WORLD_SIZE" in os.environ
    if dist:
        torch.distributed.init_process_group(backend="nccl")
        torch.cuda.set_device(int(os.environ["LOCAL_RANK"]))
    rank = int(os.environ.get("RANK", 0))

    if args.smoke:
        sys.path.insert(0, os.path.join(os.path.dirname(HERE),
                                        "from_scratch"))
        from data_tinystories import load
        train, _ = load()
        m = RoxChat(CFG_TINY)
        opt = torch.optim.AdamW(m.parameters(), lr=3e-4)
        B, CTX = 4, 128
        for s in range(20):
            i = torch.randint(0, len(train) - CTX - 1, (B,))
            x = torch.stack([train[j:j + CTX] for j in i])
            y = torch.stack([train[j + 1:j + CTX + 1] for j in i])
            opt.zero_grad()
            logits, aux, _ = m(x)
            (F.cross_entropy(logits.view(-1, 256), y.view(-1))
             + 0.01 * aux).backward()
            opt.step()
        print("[train_ddp] smoke OK (20 tiny steps, dist=%s)" % dist)
        return

    # --- rental path (needs GPUs + staged datamix; NOT run here) ---
    from rental_guardian import Watchdog
    w = Watchdog(plan_min=60 * 20)
    m = get_model(CFG_500M_50K, dist)
    opt = torch.optim.AdamW(m.parameters(), lr=3e-4, betas=(0.9, 0.95),
                            weight_decay=0.1)
    total_steps = int(args.tokens_b * 1e9 / args.batch_tokens)
    state = {"step": 0}
    os.makedirs(args.ckpt, exist_ok=True)
    if rank == 0:
        print(json.dumps({"params_M": m.n_params() / 1e6
                          if hasattr(m, "n_params") else "fsdp",
                          "total_steps": total_steps}, indent=1),
              flush=True)
    # NOTE: dataloader over staged datamix shards plugs in here
    # (streaming tokenized uint16 blocks, GPT-2 BPE). Loop skeleton:
    #   for step in range(total_steps):
    #       x, y = next_batch()
    #       ... fwd/bwd/step, sentinel probe every --sentinel-every,
    #       action = w.poll(save_fn); if action == 'over': break
    if rank == 0:
        print("[train_ddp] rental skeleton ready — needs GPUs + staged "
              "data (see datamix_60B.py + PLAN_500M_1B.md)")


if __name__ == "__main__":
    main()
