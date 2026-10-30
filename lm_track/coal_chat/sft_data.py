"""SFT pairs mined from OUR staged dialogue (data_fresh), not hand-written.

Parses 'role: content' lines, maps to user/assistant, emits single-turn
pairs (user turn + following assistant turn, optional system first).
Drops single-role fragments (e.g. lone questions with no answer) and
non-conversational junk. Deterministic sample caps per source.
Output: sft_train.jsonl / sft_val.jsonl {messages:[...]}.
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
FRESH = os.path.join(HERE, "data_fresh")
ROLEMAP = {"system": "system", "human": "user", "user": "user",
           "gpt": "assistant", "assistant": "assistant",
           "GPT": "assistant", "AI": "assistant", "bot": "assistant"}

CAP_PER_SOURCE = 1500
MIN_USER, MIN_ASST = 10, 10
MAX_TURNS_CHARS = 1500


def parse(text):
    turns = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        r, _, c = line.partition(":")
        r = r.strip()
        c = c.strip()
        if r in ROLEMAP and len(c) > 3:
            turns.append((ROLEMAP[r], c[:800]))
    if not turns:
        # No role tags (soda-style bare dialogue): alternate turns,
        # starting with user. Single blocks stay dropped downstream.
        lines = [l.strip()[:800] for l in text.split("\n") if l.strip()]
        for i, l in enumerate(lines):
            if len(l) > 20:
                turns.append(("user" if i % 2 == 0 else "assistant", l))
    return turns


def pairs_from(text):
    turns = parse(text)
    out = []
    for i, (r, c) in enumerate(turns):
        if r == "assistant" and i > 0 and turns[i - 1][0] == "user":
            sys = turns[0][1] if turns and turns[0][0] == "system" else None
            u = turns[i - 1][1]
            if len(u) >= MIN_USER and len(c) >= MIN_ASST \
                    and len(u) + len(c) <= MAX_TURNS_CHARS:
                msgs = []
                if sys:
                    msgs.append({"role": "system", "content": sys[:400]})
                msgs += [{"role": "user", "content": u},
                         {"role": "assistant", "content": c}]
                out.append(msgs)
    return out


def latin_ratio(s):
    if not s:
        return 0.0
    return sum(1 for ch in s if ord(ch) < 128) / len(s)


def build(seed=0, val_frac=0.05):
    rng = random.Random(seed)
    all_pairs = []
    for fp in sorted(os.listdir(FRESH)):
        if not fp.endswith(".jsonl"):
            continue
        src = []
        with open(os.path.join(FRESH, fp), encoding="utf-8") as f:
            for line in f:
                try:
                    t = json.loads(line).get("text", "")
                except Exception:
                    continue
                if latin_ratio(t) < 0.85:
                    continue
                for m in pairs_from(t):
                    src.append({"messages": m, "source": fp[:-6]})
                if len(src) >= CAP_PER_SOURCE * 3:
                    break
        rng.shuffle(src)
        all_pairs.extend(src[:CAP_PER_SOURCE])
        print(f"[sft_data] {fp}: {len(src[:CAP_PER_SOURCE])} pairs",
              flush=True)
    rng.shuffle(all_pairs)
    # Hash split on user text (not random rows): adjacent pairs from the
    # same dialogue share context, so a row shuffle leaks train text
    # into val and makes val loss meaningless. Same-dialog pairs still
    # occasionally split, but the systematic leak is gone.
    import hashlib
    val, train = [], []
    for d in all_pairs:
        u = d["messages"][0]["content"] if d["messages"] else ""
        h = int(hashlib.md5(u.encode("utf-8", errors="ignore")).hexdigest(),
                16) % 20
        (val if h == 0 else train).append(d)
    if len(val) < 50:  # degenerate guard
        val, train = all_pairs[:max(50, len(all_pairs) // 20)], \
            all_pairs[max(50, len(all_pairs) // 20):]
    for name, split in (("sft_train.jsonl", train),
                        ("sft_val.jsonl", val)):
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            for d in split:
                f.write(json.dumps(d) + "\n")
    print(f"[sft_data] train={len(train)} val={len(val)}")
    return train, val


if __name__ == "__main__":
    build()
