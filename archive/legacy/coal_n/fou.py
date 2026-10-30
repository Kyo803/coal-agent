"""Delta-Gated Fire-Once Units (FOU) + dense baseline.

Faithful to the proposal sec 2.2 with one documented correction:
  proposal: s_i(t) = 1 - cos_sim(x_t, x_cache_i)
  prototype: s_i(t) = ||x_t - x_cache_i||_2 (raw L2, unnormalised)

Why: on overlapping sliding windows (stride < window) consecutive inputs
are phase-shifted copies, so cosine surprise saturates near ~1.0 on every
step including stable rhythm (measured 0.96 stable vs 0.97 anomaly —
no signal). Normalising L2 by ||x_t|| also collapses the signal, because
anomaly windows grow their own denominator (measured normed 1.42 stable
vs 1.50 anomaly, while raw L2 is 3.0 vs 20.1 — 7x separation). Raw L2 is
equally cheap (one squared-difference) and the global top-k + threshold
firing logic is unchanged. Cosine remains an option for beat-aligned
(non-overlapping) inputs.

Unfired units return their cached output (zero matmul cost).
The module counts multiply-adds so we can report FLOPs saved vs dense.
"""
import math
import torch
import torch.nn as nn


class FireOnceLayer(nn.Module):
    def __init__(self, in_dim: int, n_units: int, top_k: int,
                 threshold: float = 1e-3, eps: float = 1e-8,
                 fallback_patience: int = 0):
        super().__init__()
        self.in_dim = in_dim
        self.n_units = n_units
        self.top_k = min(top_k, n_units)
        self.threshold = threshold          # inference default; may be overridden
        self.eps = eps                      # by a learned threshold (see below)
        self.fallback_patience = fallback_patience  # 0 = disabled (prototype/MVP)
        self.proj = nn.Linear(in_dim, n_units, bias=True)
        # Caches are buffers, not parameters: no grad through gating.
        self.register_buffer("x_cache", torch.zeros(n_units, in_dim))
        self.register_buffer("y_cache", torch.zeros(n_units))
        self.register_buffer("cache_init", torch.zeros(n_units, dtype=torch.bool))
        # Final-product additions: learned threshold + dense fallback.
        self.learn_thr = False
        self.tau = 1.0
        self.last_s = None
        self.reset_stats()

    def reset_stats(self):
        self.total_unit_steps = 0   # dense equivalent: T * N
        self.fired_unit_steps = 0   # actual matmuls performed
        self.fallback_events = 0    # dense-fallback steps taken
        self.unflagged_over = 0     # steps over budget NOT via fallback (must stay 0)
        self._sat_steps = 0         # consecutive budget-saturated steps

    def reset_cache(self):
        self.x_cache.zero_()
        self.y_cache.zero_()
        self.cache_init.zero_()
        self.last_s = None
        self.reset_stats()

    # ---- learned threshold (final product): thr = softplus(raw) > 0 ----
    def enable_threshold_learning(self, tau: float = 1.0):
        if not self.learn_thr:
            init = max(self.threshold, 1e-3)
            raw = math.log(math.exp(init) - 1.0 + 1e-12)  # softplus inverse
            self.raw_thr = nn.Parameter(torch.tensor(float(raw)))
            self.learn_thr = True
        self.tau = tau

    def eff_threshold(self) -> float:
        if self.learn_thr:
            with torch.no_grad():
                return float(torch.nn.functional.softplus(self.raw_thr))
        return float(self.threshold)

    def soft_active(self) -> torch.Tensor:
        """Differentiable active-fraction for the sparsity penalty."""
        assert self.last_s is not None, "soft_active needs a forward first"
        thr = torch.nn.functional.softplus(self.raw_thr)
        return torch.sigmoid((self.last_s - thr) / self.tau).mean()

    def fallback_rate(self, steps: int) -> float:
        return self.fallback_events / max(1, steps)

    @torch.no_grad()
    def forward(self, x_t: torch.Tensor):
        """Single timestep. x_t: [D]. Returns (y: [N], surprise_min, fired_idx)."""
        assert x_t.dim() == 1 and x_t.shape[0] == self.in_dim
        # Warmup: seed all caches with the first input so the trace has no
        # sentinel values (uninit caches previously reported 1e9, which
        # destroyed the warmup-percentile detector and the correlation).
        if not bool(self.cache_init.any()):
            self.x_cache[:] = x_t
            self.cache_init.fill_(True)
        # --- cheap surprise: raw L2 delta vs own cache (see note above) ---
        s = (self.x_cache - x_t).norm(dim=1).clamp(0.0, 1e9)
        self.last_s = s.detach()
        thr = self.eff_threshold()

        # --- global top-k budget over thresholded candidates ---
        eligible = torch.nonzero(s > thr, as_tuple=False).flatten()
        fallback_now = False
        if eligible.numel() == 0:
            fired = torch.empty(0, dtype=torch.long, device=x_t.device)
            self._sat_steps = 0
        elif (self.fallback_patience and eligible.numel() > self.top_k):
            # Budget exhausted again -> track saturation; on patience'th
            # consecutive saturated step, fire all eligible (dense fallback
            # for this step) so a sustained event is never starved.
            self._sat_steps += 1
            if self._sat_steps >= self.fallback_patience:
                fired = eligible
                fallback_now = True
                self.fallback_events += 1
                self._sat_steps = 0
            else:
                order = torch.argsort(s[eligible], descending=True)[:self.top_k]
                fired = eligible[order]
        else:
            self._sat_steps = 0
            order = torch.argsort(s[eligible], descending=True)[:self.top_k]
            fired = eligible[order]
        if len(fired) > self.top_k and not fallback_now:
            self.unflagged_over += 1  # structural invariant: must stay 0

        y = self.y_cache.clone()
        if fired.numel() > 0:
            w = self.proj.weight[fired]          # [k, D]
            b = self.proj.bias[fired]            # [k]
            y_new = torch.relu(w @ x_t + b)
            y[fired] = y_new
            self.x_cache[fired] = x_t
            self.y_cache[fired] = y_new
            self.cache_init[fired] = True

        self.total_unit_steps += self.n_units
        self.fired_unit_steps += int(fired.numel())
        # Global trace = MIN surprise (distance to best-matching cache).
        # Mean/max are dominated by stale caches and stay flat; min is small
        # when any cache matches the rhythm and spikes only when the input
        # matches nothing seen — i.e. genuine novelty. Firing still uses the
        # top-k most-surprised units; only the reported scalar is the min.
        return y, float(s.min()), fired

    def active_fraction(self) -> float:
        if self.total_unit_steps == 0:
            return 0.0
        return self.fired_unit_steps / self.total_unit_steps

    def flops_saved(self) -> float:
        return 1.0 - self.active_fraction()


class DenseLayer(nn.Module):
    """Dense reference: same weights as a FireOnceLayer, fires all N every step."""

    def __init__(self, fou: FireOnceLayer):
        super().__init__()
        self.proj = nn.Linear(fou.in_dim, fou.n_units, bias=True)
        with torch.no_grad():
            self.proj.weight.copy_(fou.proj.weight)
            self.proj.bias.copy_(fou.proj.bias)

    @torch.no_grad()
    def forward(self, x_t: torch.Tensor):
        return torch.relu(self.proj(x_t))
