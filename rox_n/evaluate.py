"""Batch eval: stream windows through FOU, log surprise, score vs labels, plot."""
import json
import os
import numpy as np
import torch

from .config import DEFAULT
from .fou import FireOnceLayer, DenseLayer
from . import data as data_mod

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "outputs")


def _f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    denom = 2 * tp + fp + fn
    return (2 * tp / denom) if denom else 0.0


def run(cfg=DEFAULT, out_dir=OUT, make_plots=True):
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    X, y, meta = data_mod.load(cfg)
    T, D = X.shape

    fou = FireOnceLayer(D, cfg.n_units, top_k=cfg.top_k,
                        threshold=cfg.threshold, eps=cfg.eps)
    dense = DenseLayer(fou)  # identical weights; always-on reference
    fou.reset_cache()

    surprise, active, out_norm = [], [], []
    with torch.no_grad():
        for t in range(T):
            xt = torch.from_numpy(X[t])
            y_fou, s, fired = fou(xt)
            y_dense = dense(xt)
            surprise.append(s)
            active.append(len(fired) / cfg.n_units)
            # output deviation vs dense (should be ~0 right after firing, drifts when cached)
            out_norm.append(float((y_fou - y_dense).abs().mean()))

    surprise = np.asarray(surprise)
    active = np.asarray(active)

    # Surprise as anomaly detector: threshold at 95th pct of first 20% (stable warmup).
    warm = surprise[:max(32, T // 5)]
    det_thr = float(np.percentile(warm, 95))
    y_pred = (surprise > det_thr).astype(np.int64)
    f1 = _f1(y, y_pred)
    corr = float(np.corrcoef(surprise, y)[0, 1]) if y.std() > 0 else 0.0

    metrics = {
        "source": meta["source"],
        "timesteps": T,
        "anomaly_rate": float(y.mean()),
        "config": {"n_units": cfg.n_units, "top_k": cfg.top_k,
                   "threshold": cfg.threshold, "window": cfg.window,
                   "stride": cfg.stride},
        "mean_active_fraction": float(active.mean()),
        "flops_saved_vs_dense": float(1.0 - active.mean()),
        "hard_ceiling_active": float(cfg.top_k / cfg.n_units),
        "surprise_detector_thr": det_thr,
        "surprise_f1_vs_labels": f1,
        "surprise_label_corr": corr,
        "mean_output_deviation_vs_dense": float(np.mean(out_norm)),
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    if make_plots:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = np.arange(T)
        fig, ax1 = plt.subplots(figsize=(12, 4))
        ax1.plot(xs, surprise, lw=0.8, label="mean surprise S_t")
        ax1.set_xlabel("timestep (window index)")
        ax1.set_ylabel("surprise  1 - cos_sim")
        ax2 = ax1.twinx()
        ax2.fill_between(xs, 0, 1, where=y > 0, alpha=0.3, step="mid",
                         label="anomaly label")
        ax2.set_ylim(0, 1.05)
        ax2.set_ylabel("label")
        ax1.set_title(f"ROX-N FOU prototype — surprise vs labels ({meta['source']})")
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, "surprise_vs_labels.png"), dpi=120)
        plt.close(fig)

        fig2, ax = plt.subplots(figsize=(12, 2.5))
        ax.plot(xs, active, lw=0.8)
        ax.set_xlabel("timestep")
        ax.set_ylabel("fraction of units fired")
        ax.set_title("Active compute per timestep (dense = 1.0)")
        fig2.tight_layout()
        fig2.savefig(os.path.join(out_dir, "active_fraction.png"), dpi=120)
        plt.close(fig2)

    print(json.dumps(metrics, indent=2))
    print(f"[eval] plots + metrics in {out_dir}")
    print(f"[eval] SUCCESS check: corr={corr:.3f} f1={f1:.3f} "
          f"active={metrics['mean_active_fraction']:.3f} "
          f"(saved={metrics['flops_saved_vs_dense']:.1%})")
    return metrics


if __name__ == "__main__":
    run()
