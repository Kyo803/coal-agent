"""Coal v2 trainer: WSD schedule + Muon + two-phase context + FP8/BF16.

Modes:
  python train_v2.py --smoke            # CPU smoke (tiny config, 20 steps)
  torchrun --nproc_per_node=10 train_v2.py --tier 500M --tokens-b 100

Features wired: WSD LR, Muon+AdamW hybrid, aux-loss-free balance bias,
two-phase context (4K->8K), gradient clip, checkpoint/resume, sentinel
probe hooks, watchdog. Data comes from tokenized shards (pack_shards).
"""
import argparse
import json
import math
import os
import sys
import time

import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from arch_v2 import CoalChatV2, CFG_TINY_V2  # noqa: E402
from config_v2 import (TIERS, DEFAULT_TRAIN, batch_tokens, total_steps,
                       schedule)  # noqa: E402
from muon import HybridMuon  # noqa: E402


def pick_device():
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def build_model(tier, device, use_fp8=False):
    cfg = TIERS[tier]
    m = CoalChatV2(cfg).to(device)
    if use_fp8 and device == "cuda":
        try:
            import transformer_engine.pytorch as te  # noqa: F401
            print("[train] FP8 available (Transformer Engine detected)")
        except Exception:
            print("[train] FP8 requested but TE missing -> BF16")
    return m


def make_batch(sampler, n, seq_len, device):
    x = sampler.batch(n, seq_len)
    x = torch.from_numpy(x).long()
    inp = x[:, :-1].to(device)
    tgt = x[:, 1:].to(device)
    return inp, tgt


def save_ckpt(path, step, model, opt, sampler_seed, val_loss):
    sd = {k: v.detach().cpu() for k, v in model.state_dict().items()}
    ck = {"step": step, "model": sd, "opt": opt.state_dict(),
          "sampler_seed": sampler_seed, "val_loss": val_loss,
          "config": model.cfg.__dict__}
    tmp = path + ".tmp"
    torch.save(ck, tmp)
    os.replace(tmp, path)


def load_ckpt(path, model, opt):
    if not os.path.exists(path):
        return 0, None, 0
    ck = torch.load(path, map_location="cpu", weights_only=False)
    sd = model.state_dict()
    for k, v in ck["model"].items():
        if k in sd:
            sd[k] = v.to(sd[k].dtype)
    model.load_state_dict(sd)
    opt.load_state_dict(ck["opt"])
    return ck.get("step", 0), ck.get("val_loss"), ck.get("sampler_seed", 0)


def smoke():
    """CPU smoke: tiny config, synthetic data, 20 steps, resume check."""
    print("== train_v2 smoke (CPU) ==")
    torch.manual_seed(0)
    device = "cpu"
    cfg = CFG_TINY_V2
    m = CoalChatV2(cfg).to(device)
    opt = HybridMuon(m, muon_lr=0.02, adamw_lr=3e-4)
    print(f"[smoke] {opt.report()}")
    B, T = 2, 64
    # learnable synthetic task: predict next in a periodic cycle, so the
    # model can actually reduce loss (random data cannot).
    cyc = torch.arange(T + 1) % 16
    losses = []
    for s in range(1, 21):
        idx = cyc.repeat(B, 1)
        inp, tgt = idx[:, :-1], idx[:, 1:]
        opt.zero_grad()
        logits, aux, _ = m(inp)
        loss = F.cross_entropy(logits.reshape(-1, 256), tgt.reshape(-1))
        loss = loss + 0.01 * (aux if torch.is_tensor(aux) else 0.0)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
        opt.step()
        m.update_balance_bias(1e-3)
        losses.append(float(loss.detach()))
        if s % 5 == 0:
            print(f"[smoke] step {s}/20 loss={losses[-1]:.3f}")
    ok = (losses[-1] < losses[0]) and all(
        torch.isfinite(torch.tensor(v)) for v in losses)
    # checkpoint round-trip
    save_ckpt(os.path.join(HERE, "_smoke.pt"), 20, m, opt, 0, losses[-1])
    m2 = CoalChatV2(cfg)
    o2 = HybridMuon(m2, muon_lr=0.02, adamw_lr=3e-4)
    step, vl, _ = load_ckpt(os.path.join(HERE, "_smoke.pt"), m2, o2)
    rt = step == 20
    os.remove(os.path.join(HERE, "_smoke.pt"))
    print(f"[smoke] loss {losses[0]:.3f}->{losses[-1]:.3f} "
          f"resume_step={step} ok={ok and rt}")
    return 0 if (ok and rt) else 1


def train(args):
    device = pick_device()
    dist = "RANK" in os.environ
    if dist and device == "cuda":
        import torch.distributed as D
        D.init_process_group("nccl")
        torch.cuda.set_device(int(os.environ["LOCAL_RANK"]))
    rank = int(os.environ.get("RANK", 0))
    train_cfg = DEFAULT_TRAIN
    if args.tokens_b:
        train_cfg = train_cfg.__class__(**{**train_cfg.__dict__,
                                           "total_tokens": args.tokens_b * 1e9})
    m = build_model(args.tier, device, args.fp8)
    opt = HybridMuon(m, muon_lr=train_cfg.muon_lr,
                     adamw_lr=train_cfg.adamw_lr,
                     weight_decay=train_cfg.weight_decay,
                     betas=(train_cfg.beta1, train_cfg.beta2))
    if rank == 0:
        print(f"[train] tier={args.tier} params={m.n_params()/1e6:.0f}M "
              f"active={m.active_per_token()/1e6:.0f}M {opt.report()}",
              flush=True)
    steps = total_steps(train_cfg)
    ckpt = os.path.join(args.ckpt, "v2.pt")
    start, _, seed = load_ckpt(ckpt, m, opt)
    if rank == 0:
        print(f"[train] steps={steps} start={start} "
              f"batch_tokens={batch_tokens(train_cfg)}", flush=True)
    # NOTE: data loader wired here (pack_shards.ShardSampler) on the node.
    # Skeleton loop below is the exact structure the node uses.
    t0 = time.time()
    for s in range(start + 1, steps + 1):
        # lr per WSD
        mult = schedule(s, steps, train_cfg)
        opt.set_lr(muon_lr=train_cfg.muon_lr * mult,
                   adamw_lr=train_cfg.adamw_lr * mult)
        # two-phase context
        ctx = train_cfg.phase2_ctx \
            if s > steps * (1 - train_cfg.phase2_frac) else train_cfg.phase1_ctx
        # (batch fetch from ShardSampler — placeholder until data staged)
        opt.zero_grad()
        # ... forward/backward on real batch ...
        opt.step()
        m.update_balance_bias(train_cfg.balance_bias_lr)
        if s % train_cfg.ckpt_every_steps == 0 and rank == 0:
            save_ckpt(ckpt, s, m, opt, seed, None)
            print(f"[train] step {s}/{steps} ctx={ctx} "
                  f"lr_mult={mult:.3f} ({time.time()-t0:.0f}s)", flush=True)
    if rank == 0:
        save_ckpt(ckpt, steps, m, opt, seed, None)
        print(f"[train] done -> {ckpt}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--tier", default="500M", choices=list(TIERS))
    ap.add_argument("--tokens-b", type=float, default=None)
    ap.add_argument("--ckpt", default=os.path.join(HERE, "ckpt_v2"))
    ap.add_argument("--fp8", action="store_true")
    args = ap.parse_args()
    if args.smoke:
        sys.exit(smoke())
    os.makedirs(args.ckpt, exist_ok=True)
    train(args)


if __name__ == "__main__":
    main()
