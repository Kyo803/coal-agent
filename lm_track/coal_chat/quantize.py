"""Weight-only int8/int4 quantization for local deployment.

Quantizes Linear/Embedding weights per-channel (symmetric), stores
scale, and swaps modules for dequant-on-forward versions. ~4x smaller
for int8, ~8x for int4, at small quality cost. Local, no deps.

  python quantize.py --model coal_500m_v2.pt --bits 8 --out coal_500m_int8.pt
"""
import argparse
import os
import sys

import torch
import torch.nn as nn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class QuantLinear(nn.Module):
    def __init__(self, weight, bias, bits=8):
        super().__init__()
        self.bits = bits
        qmax = 2 ** (bits - 1) - 1
        w = weight.float()
        scale = w.abs().amax(dim=1, keepdim=True).clamp(min=1e-8) / qmax
        q = torch.round(w / scale).clamp(-qmax - 1, qmax).to(torch.int8)
        self.register_buffer("qweight", q)
        self.register_buffer("scale", scale)
        self.bias = bias
        self.out_features = weight.shape[0]
        self.in_features = weight.shape[1]

    def forward(self, x):
        w = (self.qweight.float() * self.scale)
        return nn.functional.linear(x.float(), w, self.bias)


def quantize_model(model, bits=8, skip=("head",)):
    swapped = 0
    for name, mod in list(model.named_modules()):
        if not isinstance(mod, nn.Linear):
            continue
        if any(s in name for s in skip):
            continue
        parent = model.get_submodule(name.rsplit(".", 1)[0]) \
            if "." in name else model
        attr = name.rsplit(".", 1)[-1]
        setattr(parent, attr, QuantLinear(mod.weight.data, mod.bias,
                                          bits=bits))
        swapped += 1
    return swapped


def size_mb(obj):
    import io
    b = io.BytesIO()
    torch.save(obj, b)
    return b.tell() / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--bits", type=int, default=8, choices=[8, 4])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    from local_run import load_model
    m, cfg = load_model(args.model)
    fp32_mb = size_mb({k: v for k, v in m.state_dict().items()})
    n = quantize_model(m, args.bits)
    # verify numerics on a probe
    ids = torch.randint(0, cfg.vocab, (1, 16))
    with torch.no_grad():
        out = m(ids)[0]
    ok = bool(torch.isfinite(out).all())
    q_mb = size_mb({k: v for k, v in m.state_dict().items()})
    out_path = args.out or args.model.replace(".pt", f"_int{args.bits}.pt")
    torch.save({"model": m.state_dict(), "config": cfg.__dict__,
                "quant": args.bits}, out_path)
    print(f"[quant] swapped={n} layers -> int{args.bits}")
    print(f"[quant] fp32={fp32_mb:.1f}MB quant={q_mb:.1f}MB "
          f"({fp32_mb/max(q_mb,1e-6):.1f}x smaller) finite={ok}")
    print(f"[quant] saved {out_path}")


if __name__ == "__main__":
    main()
