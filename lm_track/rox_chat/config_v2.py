"""ROX N v2 configs: model tiers + training recipe + data mix.

Single source of truth for the 100B-token run. Verified by verify_arch.py
(param counts) and verify_config.py (mix sums to 1.0, paths exist).
"""
from dataclasses import dataclass, field

from arch_v2 import CFG_360M_V2, CFG_500M_V2


@dataclass(frozen=True)
class TrainCfg:
    # token budget
    total_tokens: float = 100e9
    seq_len: int = 4096
    micro_batch: int = 8            # per GPU
    grad_accum: int = 4
    # optimizer
    muon_lr: float = 0.02
    adamw_lr: float = 3e-4
    weight_decay: float = 0.1
    beta1: float = 0.9
    beta2: float = 0.95
    grad_clip: float = 1.0
    # WSD schedule (warmup-stable-decay)
    warmup_frac: float = 0.01
    stable_frac: float = 0.80
    decay_frac: float = 0.19
    # precision
    precision: str = "bf16"         # "bf16" | "fp8"
    # context extension (two-phase)
    phase1_ctx: int = 4096
    phase2_ctx: int = 8192
    phase2_frac: float = 0.15
    # balance bias update (DeepSeek-V3 aux-loss-free)
    balance_bias_lr: float = 1e-3
    # checkpointing
    ckpt_every_steps: int = 200
    # distributed
    world_size: int = 10            # 10x H200 data-parallel


@dataclass(frozen=True)
class DataMix:
    """Sampling weights per source. Must sum to 1.0."""
    fineweb_edu: float = 0.30
    code: float = 0.30
    math: float = 0.12
    conversation: float = 0.18
    instruction: float = 0.10

    def as_dict(self):
        return {"fineweb_edu": self.fineweb_edu, "code": self.code,
                "math": self.math, "conversation": self.conversation,
                "instruction": self.instruction}

    def total(self):
        return sum(self.as_dict().values())


@dataclass(frozen=True)
class SFTDataMix:
    instruction: float = 0.35
    conversation: float = 0.25
    memory_tools: float = 0.15
    safety: float = 0.10
    code_guidance: float = 0.15


# tier registry
TIERS = {
    "360M": CFG_360M_V2,
    "500M": CFG_500M_V2,
}

DEFAULT_TIER = "500M"
DEFAULT_TRAIN = TrainCfg()
DEFAULT_MIX = DataMix()
DEFAULT_SFT_MIX = SFTDataMix()

# tokenizer
VOCAB_SIZE = 50304  # GPT-2 BPE padded to multiple of 128
TOKENIZER_DIR = "tokenizer_v2"


def batch_tokens(train: TrainCfg) -> int:
    """Global tokens per optimizer step across all data-parallel ranks."""
    return train.micro_batch * train.grad_accum * train.seq_len \
        * train.world_size


def total_steps(train: TrainCfg) -> int:
    return int(train.total_tokens / batch_tokens(train))


def schedule(step: int, total: int, train: TrainCfg) -> float:
    """WSD multiplier on peak LR (linear warmup, flat, cosine-ish decay)."""
    w = int(total * train.warmup_frac)
    s = int(total * train.stable_frac)
    if step < w:
        return step / max(1, w)
    if step < s:
        return 1.0
    prog = (step - s) / max(1, total - s)
    import math
    return 0.5 * (1.0 + math.cos(math.pi * prog)) * 0.9 + 0.1


if __name__ == "__main__":
    t = DEFAULT_TRAIN
    print(f"tier={DEFAULT_TIER} tokens={t.total_tokens/1e9:.0f}B "
          f"batch_tokens={batch_tokens(t)} steps={total_steps(t)}")
    print(f"mix sum={DEFAULT_MIX.total():.3f} "
          f"{DEFAULT_MIX.as_dict()}")
    print(f"sft mix sum={sum(DEFAULT_SFT_MIX.__dict__.values()):.3f}")
    for s in (0, total_steps(t) // 100, total_steps(t) // 2,
              total_steps(t) - 1):
        print(f"  lr_mult@{s}={schedule(s, total_steps(t), t):.3f}")
