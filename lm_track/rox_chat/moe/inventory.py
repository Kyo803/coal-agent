"""Expert inventory + analysis for the ROX N 35B-A3B MoE.

Reads the GGUF and classifies every tensor into dense / shared-expert /
expert heavyweights, so we know exactly where the memory lives and what
can stay resident vs be paged.
"""
from __future__ import annotations

import json
import os
import re

from rox_config import cfg

_LAYER = re.compile(r"^blk\.(\d+)\.")


def classify(name: str) -> tuple:
    """Return (layer or '', kind)."""
    m = _LAYER.match(name)
    layer = m.group(1) if m else ""
    if name.startswith("token_embd"):
        return layer, "embd"
    if name.startswith(("output", "output_norm")):
        return layer, "output"
    if re.search(r"\.ffn_gate_inp\.weight$", name):
        return layer, "router"
    if "_shexp" in name:
        return layer, "shexp"
    if re.search(r"\.ffn_(?:up|gate|down)_exps\.weight$", name):
        return layer, "exps"
    if name.startswith("blk.") and (
            "attn_" in name or "_norm" in name or name.endswith(".bias")):
        return layer, "attn"
    if name.startswith("blk."):
        return layer, "deltanet"
    return layer, "other"


DENSE_KINDS = {"embd", "output", "attn", "deltanet", "router"}


def inventory(path: str | None = None) -> dict:
    from gguf import GGUFReader
    path = path or cfg.model_path()
    r = GGUFReader(path)
    tensors = []
    for t in r.tensors:
        layer, kind = classify(t.name)
        tensors.append({
            "name": t.name, "layer": layer, "kind": kind,
            "size": int(getattr(t, "n_bytes", 0) or 0),
            "offset": int(getattr(t, "data_offset", 0) or 0),
        })
    return {"model": os.path.basename(path), "tensors": tensors}


def save_inventory(path: str | None = None) -> dict:
    inv = inventory(path)
    out_dir = os.path.join(os.path.dirname(cfg.model_path() or "."),
                           "variants")
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "inventory.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(inv, f, indent=1)
    return inv


def load() -> dict:
    """Cached inventory (build once, reuse)."""
    out_dir = os.path.join(os.path.dirname(cfg.model_path() or "."),
                           "variants")
    p = os.path.join(out_dir, "inventory.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return save_inventory()


def stats(inv: dict) -> dict:
    tensors = inv.get("tensors", [])
    by = {}
    for t in tensors:
        by.setdefault(t["kind"], 0)
        by[t["kind"]] += t["size"]
    exps = by.get("exps", 0)
    shexp = by.get("shexp", 0)
    dense = sum(by.get(k, 0) for k in DENSE_KINDS) + by.get("other", 0)
    total = sum(by.values())
    gb = 1.0 / 1e9
    return {
        "tensors": len(tensors),
        "total_gb": round(total * gb, 2),
        "exps_gb": round(exps * gb, 2),
        "shexp_gb": round(shexp * gb, 2),
        "dense_gb": round(dense * gb, 2),
        "exps_share": round(exps / max(1, total), 3),
        "shexp_share": round(shexp / max(1, total), 3),
        "dense_share": round(dense / max(1, total), 3),
    }


def per_layer_dense(inv: dict) -> dict:
    """cumulative dense(+shexp) bytes per layer for GPU-offload budgets."""
    layers = {}
    for t in inv.get("tensors", []):
        if not t["layer"]:
            continue
        l = int(t["layer"])
        layers.setdefault(l, {"dense": 0, "shexp": 0, "exps": 0})
        if t["kind"] == "exps":
            layers[l]["exps"] += t["size"]
        elif t["kind"] == "shexp":
            layers[l]["shexp"] += t["size"]
        else:
            layers[l]["dense"] += t["size"]
    return layers


if __name__ == "__main__":
    inv = save_inventory()
    import json as _j
    print(_j.dumps(stats(inv), indent=1))