"""Live streaming runner: PLHE + FOU + EME sharing ONE surprise signal.

Per timestep t (true streaming — one window at a time, no batching):
  1. x_t              raw ECG window [D]
  2. PLHE             helix embedding e_t [4], rotation locked to signal;
                      re-estimates freq immediately iff S_{t-1} > thr,
                      else on a slow schedule (compute saved while boring)
  3. FOU              hidden h_t [N] on concat(x_t, e_t); top-k over-threshold
                      units fire, rest cached. Reports shared surprise S_t
                      = min_i ||concat - cache_i|| (novelty vs best cache).
  4. EME              1 incumbent expert iff S_t <= thr (gate skipped),
                      else full re-evaluation + all-expert mix.
  5. Baseline         dense hidden + gate + all experts, every step.

FLOP accounting is analytic multiply-add counts per step (no profiler
claims). Wall-clock ms/step is measured with perf_counter on CPU.
Anomaly detector for the accuracy readout: logit > 95th pct of warmup
(first 20%), computed identically for both paths.
"""
import time
from collections import deque

import numpy as np
import torch

from .config import MVP_DEFAULT
from . import data as data_mod
from .fou import FireOnceLayer, DenseLayer
from .plhe import HelixEmbed
from .eme import EchoRouter, dense_baseline_step


class Streamer:
    def __init__(self, cfg=MVP_DEFAULT):
        self.cfg = cfg
        base = cfg.base
        torch.manual_seed(base.seed)
        np.random.seed(base.seed + 1)
        self.rng = np.random.default_rng(base.seed + 2)

        X, y, meta = data_mod.load(base)
        self.X = X
        self.y = y
        self.meta = meta
        self.T, self.D = X.shape
        in_dim = self.D + 4

        self.fou = FireOnceLayer(in_dim, base.n_units, top_k=base.top_k,
                                 threshold=base.threshold, eps=base.eps)
        self.dense_hidden = DenseLayer(self.fou)
        self.plhe = HelixEmbed(hold_steps=cfg.plhe_hold)
        self.router = EchoRouter(in_dim, base.n_units,
                                 n_experts=cfg.n_experts, lam=cfg.eme_lambda)
        # Baseline owns its own gate + expert copies (same init, always-on).
        with torch.no_grad():
            self.base_gate = torch.nn.Linear(in_dim, cfg.n_experts)
            self.base_gate.weight.copy_(self.router.gate.weight)
            self.base_gate.bias.copy_(self.router.gate.bias)
            self.base_experts = torch.nn.ModuleList(
                torch.nn.Linear(base.n_units, 1) for _ in range(cfg.n_experts))
            for b, r in zip(self.base_experts, self.router.experts):
                b.weight.copy_(r.weight)
                b.bias.copy_(r.bias)

        L = cfg.trace_len
        self.buf_sig = deque(maxlen=L)      # raw window-centre value
        self.buf_sur = deque(maxlen=L)      # shared surprise S_t
        self.buf_act = deque(maxlen=L)      # FOU active fraction this step
        self.buf_exp = deque(maxlen=L)      # active expert id
        self.buf_coal = deque(maxlen=L)      # Coal logit
        self.buf_den = deque(maxlen=L)      # baseline logit
        self.buf_lbl = deque(maxlen=L)      # label (incl. injected)
        self.buf_ms_coal = deque(maxlen=L)
        self.buf_ms_den = deque(maxlen=L)

        self.pos = 0
        self.steps = 0
        self.inject_remaining = 0
        self.injected_total = 0
        self.prev_surprise = 0.0
        self.last_cells = [0] * cfg.unit_cells
        self.last_reeval = False
        self.last_plhe_est = False
        # analytic mult-add counters
        self.flops_coal = 0
        self.flops_den = 0

    @property
    def threshold(self):
        return self.cfg.base.threshold

    def inject(self):
        """On-demand anomaly burst trigger (front-end button)."""
        self.inject_remaining = self.cfg.inject_len

    def _next_window(self):
        x = self.X[self.pos].copy()
        label = int(self.y[self.pos])
        injected = False
        if self.inject_remaining > 0:
            burst = np.zeros_like(x)
            a0 = len(x) // 2 - 20
            burst[a0:a0 + 40] = (self.cfg.inject_amp *
                                 self.rng.standard_normal(40)).astype(np.float32)
            x = x + burst
            label = 1
            injected = True
            self.inject_remaining -= 1
            self.injected_total += 1
        self.pos = (self.pos + 1) % self.T
        return x, label, injected

    def step(self):
        """Advance exactly one timestep from the dataset stream."""
        x_np, label, injected = self._next_window()
        return self.step_from_window(x_np, label=label, injected=injected)

    def step_from_window(self, x_np, label=0, injected=False):
        """Advance one timestep from a caller-supplied window (harness use).
        Returns dict of step readouts."""
        cfg, base = self.cfg, self.cfg.base
        thr = self.fou.eff_threshold()  # learned threshold when trained
        x_np = np.asarray(x_np, dtype=np.float32)
        xt = torch.from_numpy(x_np)

        # --- Coal path (timed) ---
        t0 = time.perf_counter()
        # PLHE driven by PREVIOUS step's shared surprise (causal wiring).
        u = float(x_np.mean())
        e_t, plhe_est = self.plhe.step(u, self.prev_surprise, thr)
        feat = torch.cat([xt, torch.tensor(e_t, dtype=torch.float32)])
        h_fou, S, fired = self.fou(feat)
        self.prev_surprise = S
        coal_logit, expert_id, reeval = self.router(feat, h_fou, S, thr)
        ms_coal = (time.perf_counter() - t0) * 1000.0

        # --- dense baseline path (timed) ---
        t1 = time.perf_counter()
        h_dense = self.dense_hidden(feat)
        den_logit = dense_baseline_step(self.base_gate, self.base_experts,
                                          feat, h_dense)
        ms_den = (time.perf_counter() - t1) * 1000.0

        # --- analytic FLOPs for this step ---
        k = len(fired)
        gate_cost = (cfg.n_experts * feat.shape[0]) if reeval else 0
        exp_n = cfg.n_experts if reeval else 1
        f_coal = k * feat.shape[0] + gate_cost + exp_n * base.n_units
        f_den = (base.n_units * feat.shape[0]
                 + cfg.n_experts * feat.shape[0]
                 + cfg.n_experts * base.n_units)
        self.flops_coal += f_coal
        self.flops_den += f_den

        # --- buffers ---
        n = base.n_units
        cells = [0] * cfg.unit_cells
        per = n / cfg.unit_cells
        for f in fired.tolist():
            c = min(cfg.unit_cells - 1, int(f // per))
            cells[c] = 1
        self.last_cells = cells
        self.last_reeval = bool(reeval)
        self.last_plhe_est = bool(plhe_est)
        self.buf_sig.append(float(x_np[len(x_np) // 2]))
        self.buf_sur.append(S)
        self.buf_act.append(k / n)
        self.buf_exp.append(expert_id)
        self.buf_coal.append(coal_logit)
        self.buf_den.append(den_logit)
        self.buf_lbl.append(label)
        self.buf_ms_coal.append(ms_coal)
        self.buf_ms_den.append(ms_den)
        self.steps += 1
        return {"S": S, "k": k, "expert": expert_id, "reeval": bool(reeval),
                "coal": coal_logit, "den": den_logit, "label": label,
                "injected": injected, "ms_coal": ms_coal, "ms_den": ms_den}

    def summary(self):
        """Headline numbers for stage: savings first, accuracy second."""
        coal = np.asarray(self.buf_coal, dtype=float)
        den = np.asarray(self.buf_den, dtype=float)
        lbl = np.asarray(self.buf_lbl, dtype=int)
        n = max(32, len(coal) // 5)
        out = {
            "steps": self.steps,
            "source": self.meta["source"],
            "flops_coal": self.flops_coal,
            "flops_den": self.flops_den,
            "flops_saved": 1.0 - self.flops_coal / max(1, self.flops_den),
            "fou_active": self.fou.active_fraction(),
            "plhe_est_fraction": self.plhe.est_fraction(),
            "eme_gate_fraction": self.router.gate_fraction(),
            "eme_experts_per_step": self.router.expert_fraction(),
            "ms_coal_mean": float(np.mean(self.buf_ms_coal)) if self.buf_ms_coal else 0.0,
            "ms_den_mean": float(np.mean(self.buf_ms_den)) if self.buf_ms_den else 0.0,
            "expert": self.buf_exp[-1] if self.buf_exp else 0,
            "injected_total": self.injected_total,
        }
        if len(coal) > n and lbl.std() > 0:
            thr_r = float(np.percentile(coal[:n], 95))
            thr_d = float(np.percentile(den[:n], 95))
            pr, pd = (coal > thr_r).astype(int), (den > thr_d).astype(int)
            out["f1_coal"] = _f1(lbl, pr)
            out["f1_den"] = _f1(lbl, pd)
            out["agree"] = float((pr == pd).mean())
        else:
            out["f1_coal"] = out["f1_den"] = out["agree"] = 0.0
        return out

    def state(self):
        """JSON-safe snapshot for the front-end poll loop."""
        s = self.summary()
        s.update({
            "sig": list(self.buf_sig),
            "sur": list(self.buf_sur),
            "act": list(self.buf_act),
            "exp_trace": list(self.buf_exp),
            "coal_trace": list(self.buf_coal),
            "den_trace": list(self.buf_den),
            "lbl": list(self.buf_lbl),
            "cells": self.last_cells,
            "reeval": self.last_reeval,
            "plhe_est": self.last_plhe_est,
            "threshold": self.threshold,
            "n_experts": self.cfg.n_experts,
        })
        return s


def _f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    denom = 2 * tp + fp + fn
    return (2 * tp / denom) if denom else 0.0
