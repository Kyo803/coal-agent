"""Streaming generation over RoxChat with the shared surprise signal.

Protocol (mirrors the validated signal prototype):
  1. reset_infer(); feed the prompt, recording S per step (caches warm).
  2. Calibrate: thr = 95th pct of S over the prompt (warmup percentile,
     same method as rox_n — threshold adapts to hidden-scale, never
     hand-set per deployment).
  3. Generate: each step passes (S_prev - thr) into FOU/EME (causal
     wiring); record S trace, experts, fired fractions for the UI/eval.
No KV cache: full-prefix recompute per step. Fine at tiny scale;
production needs the KV rewrite (stated in PLAN_500M_1B, not hidden).
"""
import torch

from arch import RoxChat


class Session:
    def __init__(self, model: RoxChat):
        self.m = model
        self.thr = 0.0
        self.prev_S = 0.0
        self.trace = []

    def reset(self, prompt_ids):
        self.m.reset_infer()
        self.trace = []
        ids = torch.tensor([list(prompt_ids)])
        with torch.no_grad():
            for t in range(1, len(prompt_ids)):
                _, Sg, _ = self.m.forward_infer(ids[:, :t], 0.0)
                self.trace.append(float(Sg))
        import numpy as np
        self.thr = float(np.percentile(self.trace, 95)) \
            if self.trace else 0.0
        self.prev_S = self.trace[-1] if self.trace else 0.0
        return self.thr

    @torch.no_grad()
    def step(self, ids, do_sample=False, temp=0.7, top_p=0.9):
        logits, Sg, reeval = self.m.forward_infer(
            ids, self.prev_S - self.thr)
        self.prev_S = float(Sg)
        self.trace.append(float(Sg))
        probs = torch.softmax(logits, -1)
        if do_sample:
            sp = torch.sort(probs, descending=True)
            vals, order = sp.values, sp.indices
            mask = (vals.cumsum(-1) - vals) > top_p
            vals[mask] = 0
            vals = vals / vals.sum()
            nxt = int(order[torch.multinomial(vals, 1)])
        else:
            nxt = int(probs.argmax())
        return nxt, {"S": float(Sg), "reeval": reeval,
                     "min_prob": float(probs[nxt])}

    def generate(self, prompt_ids, n_new=64, **kw):
        ids = torch.tensor([list(prompt_ids)])
        self.reset(prompt_ids)
        outs, infos = [], []
        for _ in range(n_new):
            nxt, info = self.step(ids, **kw)
            outs.append(nxt)
            infos.append(info)
            ids = torch.cat([ids, torch.tensor([[nxt]])], 1)
            if nxt == 1:  # <eos>-ish stop for byte models
                break
        return outs, infos
