"""Talk to Coal:  python archive/legacy/mini_chat/chat.py  (type 'quit' to exit)."""
import os

import torch

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    src = os.path.join(HERE, "model")
    tok = AutoTokenizer.from_pretrained(src)
    model = AutoModelForCausalLM.from_pretrained(src,
                                                 dtype=torch.float32).eval()
    print("Coal is ready. Type 'quit' to exit.")
    hist = []
    while True:
        try:
            u = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if u.lower() in ("quit", "exit"):
            break
        if not u:
            continue
        hist.append({"role": "user", "content": u})
        p = tok.apply_chat_template(hist[-6:], tokenize=False,
                                    add_generation_prompt=True)
        enc = tok(p, return_tensors="pt")
        n = enc.input_ids.shape[1]
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=120, do_sample=True,
                                 temperature=0.7, top_p=0.9)
        txt = tok.decode(out[0][n:], skip_special_tokens=True).strip()
        hist.append({"role": "assistant", "content": txt})
        print(f"coal: {txt}")


if __name__ == "__main__":
    main()
