"""Phase-Locked Helix Embedding (PLHE), MVP-simplified.

Proposal sec 2.1: embedding rotation rate locks to the signal's local
dominant frequency instead of a fixed clock.

Two simplifications, both documented:
1. Frequency estimate = zero-crossing period of a detrended scalar buffer
   (window means), O(W) with tiny constants — no FFT in the MVP.
2. Phase is INTEGRATED (theta += omega per step), never recomputed as
   omega*t, so a change in estimated frequency cannot cause a phase jump.

Shared-surprise wiring (the actual architectural claim): the single
surprise scalar S (computed by the FOU layer, see stream.py) drives PLHE.
  S <= threshold : hold last omega, re-estimate on a slow schedule (every
                   `hold_steps`) -> frequency-estimation compute is skipped
                   most steps while the world is boring.
  S >  threshold : re-estimate immediately -> fast re-lock on events.

et = [cos theta, sin theta, r, z], r = normalised |u|, z = normalised time.
"""
import math
from collections import deque


class HelixEmbed:
    def __init__(self, buf_len=256, hold_steps=8, min_period=20, max_period=200):
        self.buf = deque(maxlen=buf_len)
        self.buf_len = buf_len
        self.hold_steps = hold_steps
        self.min_period = min_period
        self.max_period = max_period
        self.theta = 0.0
        self.omega = 2 * math.pi / 80.0  # neutral init (~mid-range period)
        self.steps_since_est = hold_steps  # force estimate on first step
        self.est_count = 0                 # freq estimations performed
        self.step_count = 0                # total steps (dense = est every step)
        self.r_max = 1e-3

    def _estimate_period(self):
        """Zero-crossing period on detrended buffer. Returns steps/cycle."""
        n = len(self.buf)
        if n < self.max_period * 2:
            return None
        xs = list(self.buf)
        mu = sum(xs) / n
        c = [v - mu for v in xs]
        # upward zero crossings
        ups = [i for i in range(1, n) if c[i - 1] <= 0 < c[i]]
        if len(ups) < 3:
            return None
        gaps = [b - a for a, b in zip(ups, ups[1:])]
        period = sum(gaps) / len(gaps)
        if not (self.min_period <= period <= self.max_period):
            return None
        return period

    def reset(self):
        self.buf.clear()
        self.theta = 0.0
        self.omega = 2 * math.pi / 80.0
        self.steps_since_est = self.hold_steps
        self.est_count = 0
        self.step_count = 0
        self.r_max = 1e-3

    def step(self, u_t: float, surprise: float, threshold: float):
        """Advance one streaming step. Returns (e_t[4], estimated_this_step)."""
        self.buf.append(float(u_t))
        self.step_count += 1
        self.steps_since_est += 1
        forced = surprise > threshold
        if forced or self.steps_since_est >= self.hold_steps:
            period = self._estimate_period()
            if period is not None:
                self.omega = 2 * math.pi / period
            self.steps_since_est = 0
            self.est_count += 1
            estimated = True
        else:
            estimated = False
        self.theta = (self.theta + self.omega) % (2 * math.pi)
        au = abs(float(u_t))
        if au > self.r_max:
            self.r_max = au
        r = au / self.r_max
        z = min(1.0, self.step_count / 5000.0)
        return [math.cos(self.theta), math.sin(self.theta), r, z], estimated

    def est_fraction(self) -> float:
        """Fraction of steps that paid for frequency estimation (dense = 1.0)."""
        if self.step_count == 0:
            return 0.0
        return self.est_count / self.step_count
