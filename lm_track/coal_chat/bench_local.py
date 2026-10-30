"""Local performance benchmark: latency, RAM, and compute per token.

  python bench_local.py --tier 500M --seq 512 --runs 5

Reports: forward latency, tokens/s, active-param fraction, estimated
RAM (fp16/int8/int4), and the FOU/EME savings vs a dense equivalent.
"""
import argparse
import os
import sys
import time

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from arch_v2 import CoalChatV2  # noqa: E402
from config_v2 import TIERS  # noqa: E402


def ram_estimate(n_params):
    return {
        "fp16_GB": round(n_params * 2 / 1e9, 2),
        "int8_GB": round(n_params * 1 / 1e9, 2),
        "int4_GB": round(n_params * 0.5 / 1e9, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="500M", choices=list(TIERS))
    ap.add_argument("--seq", type=int, default=256)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args()

    m = CoalChatV2(TIERS[args.tier]).eval()
    tot = m.n_params()
    act = m.active_per_token()
    print(f"[bench] tier={args.tier} total={tot/1e6:.0f}M "
          f"active={act/1e6:.0f}M ({act/tot:.0%})")
    print(f"[bench] RAM est: {ram_estimate(tot)}")

    idx = torch.randint(0, m.cfg.vocab, (args.batch, args.seq))
    # warmup
    with torch.no_grad():
        m(idx)
    ts = []
    with torch.no_grad():
        for _ in range(args.runs):
            t0 = time.perf_counter()
            m(idx)
            ts.append(time.perf_counter() - t0)
    mean = sum(ts) / len(ts)
    tok_s = args.batch * args.seq / mean
    print(f"[bench] forward {mean*1000:.1f} ms  "
          f"{tok_s:.0f} tok/s (batch={args.batch} seq={args.seq})")

    # dense-equivalent comparison (all experts fire)
    dense_active = m.cfg.layers * (
        (m.cfg.heads * m.cfg.head_dim + 2 * m.cfg.n_kv_heads * m.cfg.head_dim
         + m.cfg.heads * m.cfg.head_dim) * m.cfg.d)
    n_moe = sum(1 for i in range(m.cfg.layers)
                if i % m.cfg.moe_every == m.cfg.moe_every - 1)
    he = int(m.cfg.d * m.cfg.expert_mult)
    dense_active += n_moe * m.cfg.experts * 3 * m.cfg.d * he
    dense_active += (m.cfg.layers - n_moe) * 3 * m.cfg.d * int(
        m.cfg.d * m.cfg.ffn_mult)
    print(f"[bench] dense-equiv active={dense_active/1e6:.0f}M "
          f"-> sparse saves {1 - act/dense_active:.0%} compute/token")


if __name__ == "__main__":
    main()
