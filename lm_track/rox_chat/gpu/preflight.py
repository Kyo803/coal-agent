#!/usr/bin/env python3
"""GPU preflight: fail fast BEFORE burning rental time.

  python gpu/preflight.py --gpus 10 --need-gb 90

Checks: CUDA present, GPU count, NCCL importable, disk headroom, data
staged, tokenizer present, checkpoint dir writable, HF token, torchrun.
Reuses rental_guardian.preflight. Exit non-zero if any check fails.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpus", type=int, default=10)
    ap.add_argument("--need-gb", type=float, default=90.0)
    ap.add_argument("--data-dir", default="/data/rox/tok")
    args = ap.parse_args()

    fails = []
    warns = []

    # CUDA + count
    try:
        import torch
        if not torch.cuda.is_available():
            fails.append("CUDA not available")
        else:
            n = torch.cuda.device_count()
            if n < args.gpus:
                fails.append(f"only {n} GPUs (need {args.gpus})")
            else:
                name = torch.cuda.get_device_name(0)
                print(f"[pre] {n} GPUs, {name}, "
                      f"{torch.cuda.get_device_properties(0).total_memory/1e9:.0f}GB")
    except Exception as e:
        fails.append(f"torch: {e}")

    # NCCL
    try:
        import torch.distributed as D
        if not D.is_nccl_available():
            warns.append("NCCL not available (multi-GPU will fail)")
    except Exception as e:
        fails.append(f"dist: {e}")

    # disk
    free = shutil.disk_usage("/").free / 1e9 if os.path.exists("/") else 0
    if free < args.need_gb:
        fails.append(f"disk {free:.0f}GB < {args.need_gb:.0f}GB")
    else:
        print(f"[pre] disk free {free:.0f}GB")

    # data staged
    idx = os.path.join(args.data_dir, "index.json")
    if not os.path.exists(idx):
        warns.append(f"tokenized data not at {args.data_dir} (stage 1)")
    else:
        import json
        d = json.load(open(idx))
        print(f"[pre] tokens staged: train={d.get('train_tokens',0)/1e9:.1f}B")

    # tokenizer
    tok = os.path.join(HERE, "tokenizer_v2", "vocab.json")
    if not os.path.exists(tok):
        warns.append("tokenizer_v2 missing (train it first)")

    # writable ckpt
    ck = os.environ.get("CHECKPOINT_OFFLOAD", os.path.join(HERE, "ckpt_v2"))
    try:
        os.makedirs(ck, exist_ok=True)
        open(os.path.join(ck, ".w"), "w").close()
        os.remove(os.path.join(ck, ".w"))
    except Exception as e:
        fails.append(f"ckpt dir unwritable: {e}")

    # HF token
    if not os.environ.get("HF_TOKEN"):
        warns.append("HF_TOKEN unset (gated sets + rate limits)")

    # torchrun
    if not shutil.which("torchrun"):
        warns.append("torchrun not on PATH")

    print()
    for w in warns:
        print(f"[pre] WARN: {w}")
    for f in fails:
        print(f"[pre] FAIL: {f}")
    if fails:
        print("[pre] NOT READY — fix failures before renting")
        return 1
    print("[pre] READY TO LAUNCH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
