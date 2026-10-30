"""Merge LoRA adapters from ckpt_sft.pt into base and save coal_brain/.

Usage (early stop or after training):
  python merge_now.py
Requires RAM for one model load (~3GB free). No training.
"""
import os

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
CKPT = os.path.join(HERE, "ckpt_sft.pt")
OUT = os.path.join(HERE, "coal_brain")


def main():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import lora as lora_mod
    import sys
    sys.path.insert(0, HERE)
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16)
    lora_mod.attach(model)
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    print(f"[merge] checkpoint step {ck['step']}")
    for name, p in model.named_parameters():
        if name in ck["adapters"]:
            p.data.copy_(ck["adapters"][name].to(p.dtype))
    lora_mod.merge_all(model)
    lora_mod.strip_adapters(model)
    # sanity: no wrapper keys may survive into the checkpoint
    keys = set(model.state_dict().keys())
    assert not any(".base.weight" in k or k.endswith(".A") or k.endswith(".B")
                   for k in keys), "adapter keys leaked into save"
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f"[merge] saved {OUT} from step {ck['step']}")


if __name__ == "__main__":
    main()
