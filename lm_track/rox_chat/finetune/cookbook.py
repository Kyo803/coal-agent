"""Generate the QLoRA training script + runbook for a rental GPU.

The heavy training runs off-machine (a $10-15 GPU rental). This produces
exactly what to run there, using the HF source already on disk
(D:\\ROX_N_HF\\...).
"""
from __future__ import annotations

from rox_config import cfg


def base_model() -> str:
    return cfg.model.get("hf_source") or "Qwen/Qwen3.6-35B-A3B"


def train_script(hf_source: str | None = None,
                 out_dir: str = "rox-n-lora",
                 max_steps: int = 400) -> str:
    base = hf_source or base_model()
    return f'''"""QLoRA fine-tune for ROX N (run on a rented GPU).
pip install -U transformers peft trl bitsandbytes datasets accelerate
python train_qlora.py
"""
import torch
from datasets import load_dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          BitsAndBytesConfig)
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

BASE = r"{base}"
DATA = "dataset.jsonl"
OUT = r"{out_dir}"

tok = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)
ds = load_dataset("json", data_files=DATA, split="train")

bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                         bnb_4bit_use_double_quant=True,
                         bnb_4bit_compute_dtype=torch.bfloat16)
model = AutoModelForCausalLM.from_pretrained(
    BASE, quantization_config=bnb, device_map="auto",
    trust_remote_code=True)
model = get_peft_model(model, LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
    task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"]))

def fmt(ex):
    msgs = ex["messages"]
    ex["text"] = tok.apply_chat_template(msgs, tokenize=False)
    return ex
ds = ds.map(fmt)

args = SFTConfig(output_dir=OUT, max_steps={max_steps},
                 per_device_train_batch_size=1, gradient_accumulation_steps=8,
                 learning_rate=1e-4, logging_steps=10, save_steps=100,
                 bf16=True, gradient_checkpointing=True,
                 max_seq_length=2048, report_to="none")
SFTTrainer(model=model, args=args, train_dataset=ds,
           processing_class=tok).train()
model.save_pretrained(OUT)
tok.save_pretrained(OUT)
print("done ->", OUT)
'''


def runbook(hf_source: str | None = None) -> str:
    base = hf_source or base_model()
    return f"""# ROX N QLoRA runbook

1. Rent a GPU (24-48 GB): ~$10-15 for 5-10 GPU-hours.
2. Copy `dataset.jsonl` and `train_qlora.py` to the rental.
3. Base model HF source: `{base}`
   (upload it, or pull from the Hub).
4. `pip install -U transformers peft trl bitsandbytes datasets accelerate`
5. `python train_qlora.py`  -> `rox-n-lora/` adapter.
6. Download the adapter back and merge (optional):
   `peft` merge into the base, then quantize back to GGUF for llama-server.
7. Point config.model.gguf at the new file and restart.

The adapter teaches ROX N the knowledge in its own notes — reading becomes
behavior.
"""
