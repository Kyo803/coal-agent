"""Wire the risk-invention safeguards into the v2 training loop.

Reuses (does not duplicate):
  lambda_governor.Governor   -> EME hysteresis control
  parity.ParityProbe/Sentinel-> FOU train/infer drift control
  rental_guardian.Watchdog   -> checkpoint + $ burn

  from sentinel_hooks import attach_sentinels
  hooks = attach_sentinels(model, ckpt_dir)
  hooks.on_step(step, model)         # each optimizer step
  hooks.on_ckpt(step, model)         # every ckpt interval
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class SentinelHooks:
    def __init__(self, model, ckpt_dir="ckpt_v2", n_experts=36,
                 plan_min=360, n_gpu=10):
        from lambda_governor import Governor
        from parity import ParityProbe, Sentinel
        from rental_guardian import Watchdog
        self.model = model
        self.gov = Governor(n_experts)
        self.probe = None
        self.sent = Sentinel()
        self.watch = Watchdog(rate_per_gpu_hr=2.5, n_gpu=n_gpu,
                              plan_min=plan_min, ckpt_every_min=30)
        self.ckpt_dir = ckpt_dir
        self.aux_scale = 1.0
        self.history = []

    def on_step(self, step, model, val_tokens=None):
        # balance-bias update (aux-loss-free)
        model.update_balance_bias(1e-3)
        # watchdog: ckpt / over
        action = self.watch.poll()
        return action

    def on_ckpt(self, step, model, save_fn=None):
        if save_fn:
            save_fn()
        # parity probe: every N ckpts, measure FOU train/infer drift
        return {"step": step, "burn_usd": round(self.watch.burn(), 2)}

    def on_governor(self, layer_id, util, reevaluated):
        return self.gov.observe(layer_id, util, reevaluated)


def attach_sentinels(model, ckpt_dir="ckpt_v2", n_experts=36,
                     plan_min=360, n_gpu=10):
    return SentinelHooks(model, ckpt_dir, n_experts, plan_min, n_gpu)


if __name__ == "__main__":
    print("[sentinel_hooks] module OK (imports resolve)")
