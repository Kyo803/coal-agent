"""Talk to Coal-0: raw continuation chat. No prompts, no templates, no
pretrained weights — your words in, model's continuation out.
  python chat_raw.py
"""
import os
import sys

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from model_gpt import TinyGPT, sample  # noqa: E402


def main():
    model = TinyGPT()
    model.load_state_dict(torch.load(os.path.join(HERE, "rox0.pt"),
                                     weights_only=True))
    print("Coal-0 (from scratch, 0.9M params). Type and it continues. "
          "'quit' exits.")
    while True:
        try:
            u = input("you: ")
        except (EOFError, KeyboardInterrupt):
            break
        if u.strip().lower() in ("quit", "exit"):
            break
        if not u.strip():
            continue
        print("coal-0: " + sample(model, u + " ", n_new=100).strip())


if __name__ == "__main__":
    main()
