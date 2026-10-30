"""Export + quantisation bench (final product).

- ONNX: exports the dense-equivalent graph (no data-dependent control
  flow — the adaptive scheduler stays in the runtime, same split as
  production MoE deployments). Verifies numerics vs torch when
  onnxruntime is available, else exports + reports size only.
- quant_bench: dynamic int8 vs fp32 on CPU — real size + latency numbers.
- TensorRT / power draw need target hardware: see bench/measure_power.py
  and docs/edge_checklist.md. Nothing here is claimed without running it.
"""
import io
import time

import numpy as np
import torch
import torch.nn as nn


class DenseEquivalent(nn.Module):
    """Pure-dense twin of one Coal step (feat -> logit), exportable."""

    def __init__(self, streamer):
        super().__init__()
        self.hidden = nn.Linear(streamer.fou.proj.in_features,
                                streamer.fou.n_units)
        self.gate = nn.Linear(streamer.router.gate.in_features,
                              streamer.router.n_experts)
        self.experts = nn.ModuleList(
            nn.Linear(streamer.fou.n_units, 1)
            for _ in range(streamer.router.n_experts))
        with torch.no_grad():
            self.hidden.weight.copy_(streamer.fou.proj.weight)
            self.hidden.bias.copy_(streamer.fou.proj.bias)
            self.gate.weight.copy_(streamer.router.gate.weight)
            self.gate.bias.copy_(streamer.router.gate.bias)
            for d, s in zip(self.experts, streamer.router.experts):
                d.weight.copy_(s.weight)
                d.bias.copy_(s.bias)

    def forward(self, feat):
        if feat.dim() == 1:
            h = torch.relu(self.hidden(feat))
            w = torch.softmax(self.gate(feat), dim=0)
            outs = torch.stack([ex(h).squeeze(-1) for ex in self.experts])
            return (w * outs).sum()
        h = torch.relu(self.hidden(feat))              # [B, N]
        w = torch.softmax(self.gate(feat), dim=1)      # [B, E]
        outs = torch.stack([ex(h).squeeze(-1)          # [B, E]
                            for ex in self.experts], dim=1)
        return (w * outs).sum(dim=1)                   # [B]


def to_onnx(streamer, path, verify_samples=16):
    try:
        import onnx  # noqa: F401
    except ImportError as e:
        with torch.no_grad():
        diffs = [abs(float(model(f)) - float(qmodel(f.unsqueeze(0))[0]))
                 for f in feats[:50]]

    return {"ok": False, "reason": f"onnx not installed: {e}"}
    model = DenseEquivalent(streamer).eval()
    D = streamer.fou.proj.in_features
    dummy = torch.randn(D)
    torch.onnx.export(model, dummy, path, input_names=["feat"],
                      output_names=["logit"], dynamo=False)
    import os
    size = os.path.getsize(path)
    out = {"ok": True, "path": path, "bytes": size, "numeric_check": "skipped"}
    try:
        import onnxruntime as ort
        sess = ort.InferenceSession(path)
        rng = np.random.default_rng(0)
        diffs = []
        with torch.no_grad():
            for _ in range(verify_samples):
                f = rng.standard_normal(D).astype(np.float32)
                ref = float(model(torch.from_numpy(f)))
                got = float(sess.run(None, {"feat": f})[0])
                diffs.append(abs(ref - got))
        out["numeric_check"] = f"max_abs_diff={max(diffs):.2e}"
    except ImportError:
        out["numeric_check"] = "onnxruntime not installed"
    return out


def quant_bench(streamer, steps=200):
    model = DenseEquivalent(streamer).eval()
    qmodel = torch.quantization.quantize_dynamic(
        DenseEquivalent(streamer).eval(), {nn.Linear}, dtype=torch.qint8)

    def size_of(m):
        b = io.BytesIO()
        torch.save(m.state_dict(), b)
        return b.tell()

    rng = np.random.default_rng(0)
    D = streamer.fou.proj.in_features
    feats = [torch.from_numpy(rng.standard_normal(D).astype(np.float32))
             for _ in range(steps)]

    def latency(m):
        with torch.no_grad():
            for f in feats[:20]:  # warmup
                m(f)
            t0 = time.perf_counter()
            for f in feats:
                m(f)
            return (time.perf_counter() - t0) / steps * 1000.0

    with torch.no_grad():
        diffs = [abs(float(model(f)) - float(qmodel(f.unsqueeze(0))[0]))
                 for f in feats[:50]]
    return {
        "fp32_bytes": size_of(model),
        "int8_bytes": size_of(qmodel),
        "fp32_ms": round(latency(model), 4),
        "int8_ms": round(latency(qmodel), 4),
        "max_abs_logit_diff": round(float(max(diffs)), 4),
    }
