"""Instruction pre-training augmentation (InstructLM-style).

Turns raw corpus text into instruction-response pairs so the model sees
instruction format during *pretraining* (3x data efficiency per the
InstructLM paper). Three synthesizers, no external model needed:

  1. FIM (fill-in-the-middle) for code: prefix/suffix -> middle.
     Standard code-LM objective; massively improves code completion.
  2. Template instructions for code: docstring -> function, and
     "what does this do" -> explanation-from-docstring.
  3. Template instructions for prose: "summarize" / "explain" pairs
     built from the passage's own topic sentence.

  python instruction_augment.py --in D:/coal_data/code --out D:/coal_data/instr
"""
import argparse
import glob
import json
import os
import random
import re

FIM_PRE = "<|fim_prefix|>"
FIM_SUF = "<|fim_suffix|>"
FIM_MID = "<|fim_middle|>"


def is_code(text):
    code_markers = ("def ", "class ", "function ", "import ", "const ",
                    "return ", "public ", "private ", "fn ", "func ")
    return sum(text.count(m) for m in code_markers) >= 2


def fim_pair(code, rng):
    """Split code into prefix/suffix/middle at a random line boundary."""
    lines = code.split("\n")
    if len(lines) < 8:
        return None
    n = len(lines)
    cut = rng.randint(3, n - 3)
    span = rng.randint(1, max(1, (n - cut) // 2))
    pre = "\n".join(lines[:cut])
    mid = "\n".join(lines[cut:cut + span])
    suf = "\n".join(lines[cut + span:])
    if not mid.strip():
        return None
    text = f"{FIM_PRE}{pre}{FIM_SUF}{suf}{FIM_MID}{mid}"
    return {"text": text, "source": "fim"}


DOC_RE = re.compile(r'("""|\'\'\')(.*?)\1', re.S)
DEF_RE = re.compile(r"(def\s+\w+\s*\([^)]*\)\s*(?:->[^:]+)?:)")


def code_template_pair(code, rng):
    """docstring -> function, or 'what does this do' -> first docstring."""
    m = DEF_RE.search(code)
    if not m:
        return None
    sig = m.group(1)
    doc = DOC_RE.search(code[:400])
    if doc and len(doc.group(2).strip()) > 20:
        desc = doc.group(2).strip().split("\n")[0][:200]
        body = code[m.start():m.start() + 1500]
        instr = f"Write a function that {desc.lower().rstrip('.')}."
        return {"text": f"<|user|>{instr}<|assistant|>{body}",
                "source": "code_template"}
    return None


def prose_template_pair(text, rng):
    """First sentence as topic; ask to explain."""
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sents) < 4:
        return None
    topic = sents[0][:200]
    body = " ".join(sents[1:6])[:1200]
    instr = f"Explain this topic: {topic}"
    return {"text": f"<|user|>{instr}<|assistant|>{body}",
            "source": "prose_template"}


def augment(in_path, out_path, per_doc=2, seed=0):
    rng = random.Random(seed)
    n, seen = 0, 0
    with open(out_path, "w", encoding="utf-8") as out:
        for fp in sorted(glob.glob(os.path.join(in_path, "*.jsonl"))):
            if "fetch_report" in fp:
                continue
            with open(fp, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    t = d.get("text", "")
                    if len(t) < 200:
                        continue
                    seen += 1
                    pairs = []
                    if is_code(t):
                        for _ in range(per_doc):
                            p = fim_pair(t, rng)
                            if p:
                                pairs.append(p)
                        p = code_template_pair(t, rng)
                        if p:
                            pairs.append(p)
                    else:
                        p = prose_template_pair(t, rng)
                        if p:
                            pairs.append(p)
                    for p in pairs:
                        out.write(json.dumps(p) + "\n")
                        n += 1
                    if seen % 50000 == 0:
                        print(f"[instr] seen={seen} emitted={n}", flush=True)
    print(f"[instr] done: seen={seen} emitted={n} -> {out_path}")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="D:/coal_data/code")
    ap.add_argument("--out", default="D:/coal_data/instr/instr_aug.jsonl")
    ap.add_argument("--per-doc", type=int, default=2)
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    augment(args.inp, args.out, args.per_doc)


if __name__ == "__main__":
    main()
