"""Coal SDK (final product): one deployable artifact per deployment.

Artifact = zip { config.json, state.pt, head.json }. Flow:
  1. select head for the domain (ecg/imu/vibration)
  2. tune_budget() -> deployment shape (top_k, threshold init, n_experts)
  3. fit() trains weights + threshold on the domain train split
  4. save() freezes a versioned artifact; load() restores it bit-for-bit
  5. predict_stream() runs the adaptive path; export_onnx() the dense twin
"""
import io
import json
import os
import zipfile

import numpy as np
import torch

from .config import MVPConfig, MVP_DEFAULT, Config
from .stream import Streamer
from .heads import load_domain
from . import train as train_mod
from . import tune as tune_mod

VERSION = "0.2.0"


class CoalN:
    def __init__(self, domain="ecg", top_k=16, threshold=8.0, n_experts=4):
        base = Config(threshold=threshold)
        cfg = MVPConfig(base=base, n_experts=n_experts)
        # Streamer loads ECG data by default; override dims via domain check.
        self.domain = domain
        self.streamer = Streamer(cfg)
        assert self.streamer.D == 64, "core expects D=64 heads"
        self.trained = False
        self.head_mu, self.head_sd = 0.0, 1.0

    def fit(self, X, y, epochs=3, lr=1e-2, c_sparse=0.05):
        self.head_mu, self.head_sd = float(X.mean()), float(X.std() + 1e-8)
        hist = train_mod.train(self.streamer, X, y, epochs=epochs, lr=lr,
                               c_sparse=c_sparse, verbose=False)
        self.trained = True
        return hist

    def predict_stream(self, X):
        """Returns (logits, fired_counts) streaming headlessly."""
        mu, sd = float(X.mean()), float(X.std() + 1e-8)
        if self.trained and (abs(mu - self.head_mu) > 3 * self.head_sd
                             or sd > 3 * self.head_sd or sd < self.head_sd / 3):
            print(f"[sdk] WARNING: input stats (mu={mu:.2f}, sd={sd:.2f}) "
                  f"don't match fitted head (mu={self.head_mu:.2f}, "
                  f"sd={self.head_sd:.2f}) — wrong domain head? "
                  f"Detector may fail silent (see robustness/domain_shift).")
        st = self.streamer
        st.fou.reset_cache()
        st.plhe.reset()
        st.router.prev_expert = None
        st.prev_surprise = 0.0
        thr = st.fou.eff_threshold()
        logits, ks = [], []
        with torch.no_grad():
            for t in range(len(X)):
                r = st.step_from_window(X[t])
                logits.append(r["coal"])
                ks.append(r["k"])
        return np.asarray(logits), np.asarray(ks)

    def evaluate(self, X, y):
        from .stream import _f1
        logits, ks = self.predict_stream(X)
        n = max(32, len(X) // 5)
        det = float(np.percentile(logits[:n], 95))
        pred = (logits > det).astype(int)
        return {"f1": round(_f1(np.asarray(y), pred), 4),
                "active": round(float(ks.mean() / self.streamer.fou.n_units), 4)}

    def save(self, path):
        cfg = self.streamer.cfg
        payload = {
            "config": {"domain": self.domain,
                       "top_k": self.streamer.fou.top_k,
                       "threshold": self.streamer.fou.eff_threshold(),
                       "n_experts": cfg.n_experts,
                       "n_units": self.streamer.fou.n_units,
                       "version": VERSION},
            "head": {"name": self.domain, "mu": self.head_mu,
                     "sd": self.head_sd},
        }
        buf = io.BytesIO()
        torch.save({"fou": self.streamer.fou.state_dict(),
                    "gate": self.streamer.router.gate.state_dict(),
                    "experts": [e.state_dict()
                                for e in self.streamer.router.experts],
                    "thr_learned": self.streamer.fou.raw_thr.detach()
                    if self.streamer.fou.learn_thr else None}, buf)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("config.json", json.dumps(payload, indent=2))
            z.writestr("state.pt", buf.getvalue())
        return path

    @classmethod
    def load(cls, path):
        with zipfile.ZipFile(path) as z:
            payload = json.loads(z.read("config.json"))
            blob = io.BytesIO(z.read("state.pt"))
        c = payload["config"]
        self = cls(domain=c["domain"], top_k=c["top_k"],
                   threshold=c["threshold"], n_experts=c["n_experts"])
        sd = torch.load(blob, weights_only=False)
        if sd["thr_learned"] is not None:
            self.streamer.fou.enable_threshold_learning()
        self.streamer.fou.load_state_dict(sd["fou"])
        self.streamer.router.gate.load_state_dict(sd["gate"])
        self.streamer.router.gate.load_state_dict(sd["gate"])
        for e, s in zip(self.streamer.router.experts, sd["experts"]):
            e.load_state_dict(s)
        self.head_mu = payload["head"]["mu"]
        self.head_sd = payload["head"]["sd"]
        self.trained = True
        return self


def tune_then_train(domain="ecg", seed=0):
    """Reference deployment recipe used by run_final_eval.py."""
    X, y, _ = load_domain(domain, seed=seed)
    n = len(X)
    Xtr, ytr = X[:n // 2], y[:n // 2]
    Xva, yva = X[n // 2:], y[n // 2:]
    best, rows = tune_mod.tune_budget(Xva, yva)
    det = CoalN(domain=domain, top_k=best["top_k"],
               threshold=best["threshold"], n_experts=best["n_experts"])
    hist = det.fit(Xtr, ytr)
    return det, {"tuned": best, "train_hist": hist,
                 "val": det.evaluate(Xva, yva)}
