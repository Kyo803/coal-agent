"""Coal-Chat loop: sessions + TME + STR + tools + lockout, one place.

Backends (--backend tiny|hf):
  tiny: byte-level arch weights (default random = pipeline proof).
  hf:   open instruct model as the talking brain TODAY (our attachments
        around it); scratch 500M swaps in via the same interface later.
Scripted self-test: --selftest runs turns without a human.
"""
import os
import sys

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from arch import CoalChat, CFG_TINY  # noqa: E402
from generate import Session  # noqa: E402
from attachments import TurnMemory, tool_gate, lockout_check, is_social  # noqa: E402
from retrieval import BM25, str_answer  # noqa: E402
from hf_backend import norm as _norm  # noqa: E402


def build(weights=None, vocab=256):
    from arch import Cfg
    cfg = Cfg(**{**CFG_TINY.__dict__, "vocab": vocab})
    m = CoalChat(cfg)
    if weights and os.path.exists(weights):
        m.load_state_dict(torch.load(weights, weights_only=True))
    return m


QWORDS = ("what", "who", "where", "when", "why", "how", "is", "are",
          "can", "do", "does", "will", "would", "should")

COMMON = set(
    "i you he she it we they me him her us them my your his our their "
    "the a an and or but if then so because what who where when why how "
    "is are was were be been do does did can could will would should "
    "hello hi hey thanks thank please sorry yes no ok love like want "
    "know think feel sad happy good bad big small time day night man "
    "woman dog cat house car book water food die death kill life".split())


def is_gibberish(text):
    """No recognizable words + short + not math: the model will only
    pattern-complete. Route to honest rephrase instead."""
    import re as _re
    toks = [t for t in _re.findall(r"[a-z]+", text.lower())]
    if not toks or len(text) > 60:
        return False
    if _re.search(r"\d", text):
        return False
    return not any(t in COMMON or len(t) > 12 for t in toks)


def normalize_input(text):
    """Light input shaping (not answers): capitalize; add '?' to bare
    question-worded inputs. Our SFT distribution is capitalized
    questions — lowercase fragments trigger immediate EOS."""
    t = text.strip()
    if not t:
        return t
    t = t[0].upper() + t[1:]
    low = t.lower()
    if not t[-1] in ".!?" and low.split()[0] in QWORDS:
        t += "?"
    return t


def answer_turn(sess, mem, index, user_text, enc, dec, hf=None,
                s_mean_default=1.0):
    lo = lockout_check(user_text)
    if lo["locked"]:
        mem.add("assistant", lo["text"], 9.0)
        return lo["text"], "lockout"
    if hf is not None:
        model_text = normalize_input(user_text)
        if is_gibberish(user_text):
            final = ("I couldn't understand that — could you rephrase it?")
            mem.add("user", user_text, 1.0)
            mem.add("assistant", final, 1.0)
            return final, "gibberish+hf"
        # Arithmetic in the QUESTION itself short-circuits everything:
        # compute directly instead of hoping the draft contains it.
        handled, calc = tool_gate(model_text)
        if handled:
            mem.add("user", user_text, 1.0)
            mem.add("assistant", calc, 1.0)
            return calc, "calculated+hf"
        draft, minp, dn, sn = hf.draft_fn(model_text)
        if not draft.strip():
            # Empty greedy draft (common on gibberish/short inputs after
            # SFT): one sampled retry, then honest fallback — never emit
            # an empty line.
            draft = hf.retry_text(user_text)
            minp, dn, sn = 0.4, _norm(draft), [_norm(draft), ""]
        if not draft.strip():
            final = ("I couldn't understand that — could you rephrase it?")
            mem.add("user", user_text, 1.0)
            mem.add("assistant", final, 1.0)
            return final, "empty-fallback+hf"
        # Tools first: verified computation never needs retrieval.
        handled, calc = tool_gate(draft)
        if handled:
            mem.add("user", user_text, 1.0)
            mem.add("assistant", calc, 1.0)
            return calc, "calculated+hf"
        if is_social(user_text):
            # Social turns carry no factual claim: answer directly,
            # never route through retrieval (miss-refusal here is a bug).
            handled, final = tool_gate(draft)
            mem.add("user", user_text, 1.0)
            mem.add("assistant", final, 1.0)
            return final, "direct+hf"
        r = str_answer(user_text, lambda _q: (draft, minp, dn, sn),
                       index)
        if r["status"] == "retrieved":
            # Grounded regeneration (FLARE-style): the model answers
            # conditioned on the retrieved docs — [sourced] is earned,
            # not concatenated.
            ctx = " ".join(r["retrieved"])
            final = hf.regenerate(user_text, ctx)
            if not final.strip():
                # Never emit an empty answer wearing a sourced badge.
                final = ("I found relevant context but could not "
                         "formulate an answer from it.")
            else:
                final = final + " [sourced]"
        else:
            final = r["text"]
        handled, final = tool_gate(final)
        mem.add("user", user_text, 1.0)
        mem.add("assistant", final, 1.0)
        return final, r["status"] + "+hf"
    outs, infos = sess.generate(enc(user_text), n_new=48)
    draft = dec(outs)
    minp = min([i["min_prob"] for i in infos] or [1.0])
    dn = draft.lower().strip()

    def draft_fn(_q):
        with torch.no_grad():
            s2, _ = sess.generate(enc(user_text), n_new=48)
            s3, _ = sess.generate(enc(user_text), n_new=48)
        return draft, minp, dn, [dec(s2).lower().strip(),
                                 dec(s3).lower().strip()]
    r = str_answer(user_text, draft_fn, index)
    handled, final = tool_gate(r["text"])
    s_mean = sum(i["S"] for i in infos) / max(1, len(infos))
    mem.add("user", user_text, s_mean)
    mem.add("assistant", final, s_mean)
    return final, r["status"]


def main():
    weights = None
    backend = "tiny"
    selftest = "--selftest" in sys.argv
    for a in sys.argv[1:]:
        if a.startswith("--weights="):
            weights = a.split("=", 1)[1]
        if a.startswith("--backend="):
            backend = a.split("=", 1)[1]
    hf = None
    sess = None
    if backend == "hf":
        from hf_backend import HFDraft
        hf = HFDraft()
    else:
        m = build(weights)
        sess = Session(m)
    mem = TurnMemory()
    coal_docs = ["Coal is a small assistant built in the Coal project.",
                "Coal is a surprise-gated architecture: Phase-Locked "
                "Helix Embedding, Delta-Gated Fire-Once Units, and "
                "Expert Memory Echo routing share one surprise signal.",
                "Coal skips about 97 percent of multiply-adds on "
                "stable input."]
    small = BM25(coal_docs)
    big = os.path.join(HERE, "bigindex", "index.pkl")
    if os.path.exists(big):
        from bigindex import BigBM25
        big_idx = BigBM25.load(os.path.join(HERE, "bigindex"))

        class BothIndex:
            down = False

            def search(self, q, top=2):
                hits = big_idx.search(q, top=top)
                return hits if hits else small.search(q, top=top)

        index = BothIndex()
        print("[chat] corpus index: 100K passages + Coal docs")
    else:
        index = small
    enc = lambda s: list(s.encode("utf-8", errors="ignore"))[:64]

    def dec(ids):
        raw = bytes([b for b in ids if 0 <= b < 256])
        return raw.decode("utf-8", errors="ignore") \
            .encode("ascii", errors="ignore").decode()
    turns = ["Hello! Who are you?",
             "What is 17 times 19?",
             "What is the speed of light?",
             "Tell me about Coal.",
             "I want to kill myself"] if selftest else None
    print("coal-chat ready" + (" (selftest)" if selftest else ""
                              + ". 'quit' exits."))
    while True:
        try:
            u = turns.pop(0) if turns is not None else input("you: ").strip()
            if turns is not None:
                print(f"you: {u}")
        except (EOFError, KeyboardInterrupt):
            break
        if u.lower() in ("quit", "exit"):
            break
        if not u:
            continue
        out, status = answer_turn(sess, mem, index, u, enc, dec, hf=hf)
        print(f"coal [{status}]: {out}")
        if turns is not None and not turns:
            print(f"[selftest] turns={len(mem.turns)} "
                  f"ctx={len(mem.context())} OK")
            break


if __name__ == "__main__":
    main()
