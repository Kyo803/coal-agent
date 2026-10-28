"""Manual LoRA (no peft dependency): low-rank adapters on q/v projections.

Wraps a HF causal LM in place: base weights frozen, only A/B matrices
train. merge() folds adapters back for serving. Rank 8 @ 30 layers x
q+v ≈ 0.55M trainable of 134.5M — CPU-trainable, minimal distortion
(lesson from mini_chat: 35M trainable overfit 52 examples).
"""
import math

import torch
import torch.nn as nn


class LoRALinear(nn.Module):
    def __init__(self, base: nn.Linear, r=8, alpha=16.0):
        super().__init__()
        self.base = base
        self.base.weight.requires_grad = False
        if self.base.bias is not None:
            self.base.bias.requires_grad = False
        d_in, d_out = base.in_features, base.out_features
        dt = base.weight.dtype
        self.A = nn.Parameter((torch.randn(r, d_in) * (1.0 / math.sqrt(r))).to(dt))
        self.B = nn.Parameter(torch.zeros(d_out, r, dtype=dt))
        self.scale = alpha / r

    def forward(self, x):
        return self.base(x) + (x @ self.A.T @ self.B.T) * self.scale

    def merge(self):
        with torch.no_grad():
            self.base.weight += (self.B @ self.A) * self.scale


def attach(model, targets=("q_proj", "v_proj"), r=8, alpha=16.0):
    """Replace matching Linears in place. Returns adapter param count."""
    for p in model.parameters():
        p.requires_grad = False  # freeze everything; adapters opt back in
    n = 0
    for name, mod in list(model.named_modules()):
        if not isinstance(mod, nn.Linear):
            continue
        if not any(t in name for t in targets):
            continue
        parent, attr = name.rsplit(".", 1)
        holder = model.get_submodule(parent)
        lora = LoRALinear(mod, r, alpha)
        lora.A.requires_grad = True
        lora.B.requires_grad = True
        setattr(holder, attr, lora)
        n += mod.in_features * r + r * mod.out_features
    return n


def trainable_params(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def merge_all(model):
    for mod in model.modules():
        if isinstance(mod, LoRALinear):
            mod.merge()


def strip_adapters(model):
    """Replace LoRALinear wrappers with plain nn.Linear holding merged
    weights. REQUIRED before save_pretrained — otherwise the checkpoint
    stores wrapper keys (base.weight/A/B) that stock transformers
    cannot load (q/v silently random = comma-babble)."""
    import torch.nn as nn
    for name, mod in list(model.named_modules()):
        if isinstance(mod, LoRALinear):
            mod.merge()
            lin = nn.Linear(mod.base.in_features, mod.base.out_features,
                            bias=mod.base.bias is not None)
            with torch.no_grad():
                lin.weight.copy_(mod.base.weight)
                if lin.bias is not None:
                    lin.bias.copy_(mod.base.bias)
            parent, attr = name.rsplit(".", 1)
            setattr(model.get_submodule(parent), attr, lin)
    return model
