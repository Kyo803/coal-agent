"""Parity Sentinel: keeps FOU training approximation honest vs inference.

Every K train steps, run forward_infer over fixed probe prefixes and
measure mean |logit drift| against train-mode dense logits on the same
prefixes. Control loop on the sparsity aux weight:
  drift < eps        -> aux_scale decays (protect quality)
  drift rising twice -> aux_scale doubles + alert (approximation failing)
  drift > hard_stop  -> should_stop (reject approximation before GPU spend)
Probes are checked in (deterministic TinyStories prefixes) so 100M/500M
runs are directly comparable. Gate: drift <= 0.15 at Stage-0 end.
"""
import torch
import torch.nn.functional as F

PROBES = [
    "Once upon a time there was a little ",
    "The big red dog ran to the ",
    "Lily liked to play with her ",
    "One day the sun was very ",
]


def encode(s):
    return list(s.encode("utf-8", errors="ignore"))


class ParityProbe:
    def __init__(self, encode_fn, prefixes=PROBES):
        self.ids = [torch.tensor([encode_fn(p)]) for p in prefixes]

    @torch.no_grad()
    def drift(self, model):
        ds = []
        for ids in self.ids:
            train_logits, _, _ = model(ids)
            model.reset_infer()
            inf_logits = []
            for t in range(1, ids.shape[1]):
                l, _, _ = model.forward_infer(ids[:, :t], 0.0)
                inf_logits.append(l)
            inf = torch.stack(inf_logits)  # [T-1, V]
            tr = train_logits[0, :-1, :]
            ds.append(float((inf - tr).abs().mean()))
        return sum(ds) / len(ds)


class Sentinel:
    def __init__(self, eps=0.15, hard_stop=0.5, patience=2):
        self.eps = eps
        self.hard_stop = hard_stop
        self.patience = patience
        self.aux_scale = 1.0
        self.rises = 0
        self.prev = None

    def update(self, drift):
        if drift > self.hard_stop:
            return True, False  # should_stop
        if self.prev is not None and drift > self.prev:
            self.rises += 1
        else:
            self.rises = 0
        self.prev = drift
        alert = False
        if self.rises >= self.patience:
            self.aux_scale *= 2.0
            self.rises = 0
            alert = True
        if drift < self.eps:
            self.aux_scale = max(0.25, self.aux_scale * 0.9)
        return False, alert


def selftest():
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from arch import RoxChat, CFG_TINY
    torch.manual_seed(0)
    m = RoxChat(CFG_TINY)
    probe = ParityProbe(encode)
    d0 = probe.drift(m)
    assert d0 == d0 and d0 < 5.0, d0  # finite, sane at init
    s = Sentinel()
    stop, alert = s.update(d0)
    assert stop is False
    # rising drift twice -> aux doubles
    s.update(d0 + 0.01)
    stop, alert = s.update(d0 + 0.02)
    assert alert is True and s.aux_scale == 2.0, (alert, s.aux_scale)
    # hard stop
    stop, _ = s.update(99.0)
    assert stop is True
    print(f"[parity] selftest OK (init drift={d0:.3f})")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if selftest() else 1)
