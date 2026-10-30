"""Supervised training for the final product (learned weights + threshold).

What is learned: FOU projections, router gate, experts, and the surprise
threshold itself (softplus-parameterised, driven by a sparsity penalty).
What is NOT learned (by design): the hard gating decisions and caches are
detached — gradients flow only through fired units, exactly as in sparse
MoE training. PLHE has no parameters.

Loss per epoch (streamed in order, caches reset each epoch):
  L = BCE_with_logits(logits, labels; pos_weight) + c_sparse * soft_active
"""
import torch
import torch.nn as nn

from .config import MVP_DEFAULT
from .stream import Streamer


def train(streamer: Streamer, X, y, epochs=3, lr=3e-3, c_sparse=0.1,
          pos_weight=None, verbose=True):
    fou = streamer.fou
    fou.enable_threshold_learning()
    params = [fou.proj.weight, fou.proj.bias, fou.raw_thr,
              streamer.router.gate.weight, streamer.router.gate.bias]
    for ex in streamer.router.experts:
        params += [ex.weight, ex.bias]
    opt = torch.optim.Adam(params, lr=lr)
    bce = nn.BCEWithLogitsLoss(
        pos_weight=pos_weight or torch.tensor(anomaly_weight(y)))
    hist = []
    for ep in range(epochs):
        fou.reset_cache()
        streamer.plhe.reset()
        streamer.router.prev_expert = None
        streamer.prev_surprise = 0.0
        tot, n = 0.0, 0
        for t in range(len(X)):
            opt.zero_grad()
            xt = torch.from_numpy(X[t])
            u = float(X[t].mean())
            e_t, _ = streamer.plhe.step(u, streamer.prev_surprise,
                                        fou.eff_threshold())
            feat = torch.cat([xt, torch.tensor(e_t, dtype=torch.float32)])
            h, S, _ = fou(feat)
            streamer.prev_surprise = S
            logit, _, _ = streamer.router(feat, h, S, fou.eff_threshold())
            target = torch.tensor(float(y[t]))
            loss = bce(torch.tensor(logit), target) + c_sparse * fou.soft_active()
            loss.backward()
            opt.step()
            tot += float(loss.detach())
            n += 1
        hist.append({"epoch": ep, "loss": tot / n,
                     "thr": fou.eff_threshold()})
        if verbose:
            print(f"[train] epoch {ep}: loss={tot / n:.4f} "
                  f"thr={fou.eff_threshold():.3f}")
    return hist


def anomaly_weight(y) -> float:
    import numpy as np
    y = __import__("numpy").asarray(y)
    npos = max(1, int(y.sum()))
    return float((len(y) - npos) / npos)


@torch.no_grad()
def eval_stream_weights(streamer: Streamer, X, y):
    """F1 of current weights on a split (headless streaming, caches reset)."""
    import numpy as np
    fou = streamer.fou
    fou.reset_cache()
    streamer.plhe.reset()
    streamer.router.prev_expert = None
    streamer.prev_surprise = 0.0
    thr = fou.eff_threshold()
    logits = []
    for t in range(len(X)):
        xt = torch.from_numpy(X[t])
        e_t, _ = streamer.plhe.step(float(X[t].mean()),
                                    streamer.prev_surprise, thr)
        feat = torch.cat([xt, torch.tensor(e_t, dtype=torch.float32)])
        h, S, _ = fou(feat)
        streamer.prev_surprise = S
        logit, _, _ = streamer.router(feat, h, S, thr)
        logits.append(logit)
    logits = np.asarray(logits)
    n = max(32, len(logits) // 5)
    det = float(np.percentile(logits[:n], 95))
    pred = (logits > det).astype(int)
    from .stream import _f1
    return _f1(np.asarray(y), pred), streamer.fou.active_fraction()
