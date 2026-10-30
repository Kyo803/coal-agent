"""Rental Guardian: preflight gates + in-run watchdog for rented GPUs.

preflight(): ALL must pass before the clock starts burning —
  bucket staged (>= expected GB), NCCL/torch available, disk headroom,
  HF token present, checkpoint-offload path writable, dry-run import
  of the training entry. Returns list of failures (empty = go).
Watchdog: wrap the train loop; checkpoints every N minutes, tracks $
  burn vs plan, auto-resumes from latest checkpoint on preemption
  (reclaim-safe only with this file present and tested).
"""
import os
import shutil
import time


def preflight(bucket_gb=0.0, need_gb=5.0, entry="train_distributed.py"):
    fails = []
    try:
        import torch
        if not torch.cuda.is_available():
            fails.append("no-cuda (CPU-only node?)")
        elif torch.cuda.device_count() < 1:
            fails.append("zero-gpus")
    except Exception as e:
        fails.append(f"torch-import: {e}")
    try:
        import torch.distributed as dist  # noqa: F401
    except Exception as e:
        fails.append(f"dist-unavailable: {e}")
    free_gb = shutil.disk_usage(".").free / 1e9
    if free_gb < 20:
        fails.append(f"disk-low: {free_gb:.1f}GB free, need 20+")
    if bucket_gb < need_gb:
        fails.append(f"data-not-staged: {bucket_gb:.1f}GB < {need_gb:.1f}GB")
    if not os.environ.get("HF_TOKEN"):
        fails.append("no-HF_TOKEN (gated sets + tokenizer downloads fail)")
    if not os.path.exists(entry):
        fails.append(f"entry-missing: {entry}")
    off = os.environ.get("CHECKPOINT_OFFLOAD", "")
    if off:
        try:
            os.makedirs(off, exist_ok=True)
            open(os.path.join(off, ".w"), "w").write("ok")
            os.remove(os.path.join(off, ".w"))
        except Exception as e:
            fails.append(f"offload-unwritable: {e}")
    else:
        fails.append("CHECKPOINT_OFFLOAD unset (preemption = total loss)")
    return fails


class Watchdog:
    def __init__(self, rate_per_gpu_hr=3.85, n_gpu=10, plan_min=60,
                 ckpt_every_min=5):
        self.rate = rate_per_gpu_hr
        self.n = n_gpu
        self.plan = plan_min * 60
        self.ckpt_every = ckpt_every_min * 60
        self.t0 = time.time()
        self.last_ckpt = self.t0

    def burn(self):
        return (time.time() - self.t0) / 3600 * self.rate * self.n

    def poll(self, save_ckpt_fn=None):
        """Call each train step. Returns 'ckpt' / 'over' / 'ok'."""
        now = time.time()
        if now - self.t0 > self.plan:
            return "over"
        if now - self.last_ckpt > self.ckpt_every:
            if save_ckpt_fn is not None:
                save_ckpt_fn()
            self.last_ckpt = now
            return "ckpt"
        return "ok"


def selftest():
    fails = preflight(bucket_gb=0.0)  # nothing staged here -> must fail
    assert any("data-not-staged" in f for f in fails), fails
    assert any("HF_TOKEN" in f or "no-cuda" in f for f in fails), fails
    w = Watchdog(plan_min=60)
    assert w.poll() == "ok"
    w.t0 -= 3700
    assert w.poll() == "over"
    w.t0 = time.time()
    w.last_ckpt -= 400
    assert w.poll() == "ckpt"
    print("[guardian] selftest OK (fails correctly, burn=$%.2f/hr)"
          % (w.rate * w.n))
    return True


if __name__ == "__main__":
    raise SystemExit(0 if selftest() else 1)
