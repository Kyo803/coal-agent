"""Expert placement: which tensors stay resident vs page from disk.

The inventory shows dense+shared-expert ≈ 1.66 GB and experts ≈ 19.5 GB
(92%). Optimal MoE serving: push every NON-expert tensor to the GPU via
`-ot`, leave the expert heavyweights on CPU with mmap so the OS pages only
the ~8/256 experts that actually fire per token.
"""
from __future__ import annotations

DENSE_GPU_PATTERNS = [
    "token_embd.weight",
    "output.weight",
    "output_norm.weight",
    "blk.*.attn_*",
    "blk.*.*_norm*",
    "blk.*.ssm_*",
    "blk.*.ffn_*shexp*",
    "blk.*.ffn_gate_inp*",
]


def placement_args(inv=None, vram_budget_gb: float | None = None) -> list:
    """Return llama-server args: `-ngl 0` + dense/shared -> GPU0, experts
    stay on CPU (mmap-pageable)."""
    if vram_budget_gb is not None:
        from . import inventory as I
        inv = inv or I.load()
        st = I.stats(inv)
        need = st["dense_gb"] + st["shexp_gb"]
        if need > vram_budget_gb:
            # GPU too small for everything: fall back to CPU-only, no -ot
            return []
    ot = ",".join(f"{p}=Vulkan0" for p in DENSE_GPU_PATTERNS)
    return ["-ot", ot]


def feasibility() -> dict:
    from . import inventory as I
    inv = I.load()
    st = I.stats(inv)
    return {"dense_gb": st["dense_gb"], "shexp_gb": st["shexp_gb"],
            "needed_vram_gb": round(st["dense_gb"] + st["shexp_gb"], 2),
            "exps_gb": st["exps_gb"],
            "fits_8gb": (st["dense_gb"] + st["shexp_gb"]) <= 6.5}