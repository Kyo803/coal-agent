"""HF instruct backend for coal-chat: a real talking brain behind our
attachments today; scratch 500M brain swaps in when trained (same
draft_fn interface, zero pipeline changes).

Draft = greedy decode (min token prob recorded); disagreement = 2 extra
samples, normalized exact-match (discrete semantic-entropy family).
Output-side signals carry the STR decision, per trigger_spec.md.
"""
import re

import torch


def norm(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class HFDraft:
    def __init__(self, model_id="HuggingFaceTB/SmolLM2-135M-Instruct",
                 max_new=80, prefer_local=True):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import os as _os
        # Prefer OUR trained weights when they exist; fall back to base.
        # prefer_local=False forces the named upstream model (eval use).
        local = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                              "coal_brain")
        src = local if (prefer_local and _os.path.isdir(local)) else model_id
        print("[hf_backend] model source: %s"
              % ("coal_brain (ours)" if src == local else "base"))
        self.tok = AutoTokenizer.from_pretrained(src)
        self.model = AutoModelForCausalLM.from_pretrained(
            src, dtype=torch.float32).eval()
        self.max_new = max_new
        self.history = []

    def prompt(self, user_text):
        self.history.append({"role": "user", "content": user_text})
        sys = {"role": "system",
               "content": "You are Coal, a small assistant built in the "
                          "Coal project. Answer briefly."}
        msgs = [sys] + self.history[-6:]
        try:
            return self.tok.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True)
        except Exception:
            return "You are Coal. User: " + user_text + "\nAssistant:"

    def _gen(self, prompt, greedy=True):
        enc = self.tok(prompt, return_tensors="pt")
        n = enc.input_ids.shape[1]
        # min_new_tokens: SFT taught early-EOS; never accept a stillborn
        # draft — force at least a few tokens before EOS may fire.
        kw = dict(max_new_tokens=self.max_new, min_new_tokens=5)
        with torch.no_grad():
            if greedy:
                out = self.model.generate(
                    **enc, do_sample=False, return_dict_in_generate=True,
                    output_scores=True, **kw)
                ids = out.sequences[0][n:]
                probs = [float(torch.softmax(s, -1)[0, t])
                         for s, t in zip(out.scores, ids)]
                txt = self.tok.decode(ids, skip_special_tokens=True)
                return txt, (min(probs) if probs else 0.0)
            s = self.model.generate(**enc, do_sample=True, temperature=0.7,
                                    top_p=0.9, **kw)
            return self.tok.decode(s[0][n:], skip_special_tokens=True)

    def draft_fn(self, user_text):
        p = self.prompt(user_text)
        draft, minp = self._gen(p, greedy=True)
        s2 = self._gen(p, greedy=False)
        s3 = self._gen(p, greedy=False)
        self.history.append({"role": "assistant", "content": draft})
        dn = norm(draft)
        return draft.strip(), minp, dn, [norm(s2), norm(s3)]

    def retry_text(self, user_text):
        """Sampled retry that never touches history (no pollution from
        failed attempts). Returns '' if still empty."""
        msgs = self.history[-6:]
        try:
            p = self.tok.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True)
        except Exception:
            p = "User: " + user_text + "\nAssistant:"
        return self._gen(p, greedy=False).strip()

    def regenerate(self, user_text, ctx, max_new=None):
        """Grounded pass: answer using ONLY the retrieved context.
        History untouched (no pollution from draft attempts)."""
        msgs = [{"role": "system",
                 "content": "You are Coal. Answer briefly using ONLY the "
                            "context below. If it is insufficient, say so."},
                {"role": "user",
                 "content": f"Context: {ctx}\nQuestion: {user_text}"}]
        try:
            p = self.tok.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True)
        except Exception:
            p = f"Context: {ctx}\nQuestion: {user_text}\nAnswer:"
        txt, _ = self._gen(p, greedy=True)
        return txt.strip()
