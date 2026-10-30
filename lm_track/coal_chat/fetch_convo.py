"""Fetch fresh conversational + English-teaching data (local staging).

Streams each HF set, extracts plain dialogue/text, writes unified JSONL
{text, source} capped per source. Gated/404 sources are SKIPPED with a
logged reason (never fatal — manifest renormalizes without them).
FineWeb-Edu is SAMPLED (3GB local; full 25B streams on-node per manifest).
  python fetch_convo.py [--only tag] [--outdir DIR]
Report: fetch_report.json {per-source bytes, rows, status} (merged).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "data_fresh")
GB = 1024 ** 3

SOURCES = [
    # (tag, hf_id, config, split, cap_bytes)
    ("slimorca", "Open-Orca/SlimOrca", None, "train", 4 * GB),
    ("openhermes", "teknium/OpenHermes-2.5", None, "train", 8 * GB),
    ("oasst2", "OpenAssistant/oasst2", None, "train", 3 * GB),
    ("oasst1", "OpenAssistant/oasst1", None, "train", 3 * GB),
    ("soda", "allenai/soda", None, "train", 3 * GB),
    ("ultrachat", "HuggingFaceH4/ultrachat_200k", "default", "train_sft",
     5 * GB),
    ("hh_rlhf", "Anthropic/hh-rlhf", "default", "train", 2 * GB),
    ("lmsys", "lmsys/lmsys-chat-1m", None, "train", 8 * GB),
    ("wildchat", "allenai/WildChat-1M", None, "train", 8 * GB),
    ("fineweb_edu", "HuggingFaceFW/fineweb-edu", "CC-MAIN-2024-51",
     "train", 3 * GB),
    ("sharegpt", "anon8231489123/ShareGPT_Vicuna_unfiltered", None,
     "train", 4 * GB),
    ("orca_math", "microsoft/orca-math-word-problems-200k", None,
     "train", 2 * GB),
    ("no_robots", "HuggingFaceH4/no_robots", None, "train", 1 * GB),
    ("shp", "stanfordnlp/SHP", None, "train", 2 * GB),
    ("ultrafeedback", "HuggingFaceH4/ultrafeedback_binarized", None,
     "train_sft", 1 * GB),
    ("openwebtext", "Skylion007/openwebtext", None, "train", 3 * GB),
    ("full_hh", "Dahoas/full-hh-rlhf", None, "train", 3 * GB),
    ("ultrafeedback_full", "openbmb/UltraFeedback", None,
     "train", 4 * GB),
    ("prosocial", "allenai/prosocial-dialog", None, "train", 2 * GB),
    ("platypus", "garage-bAInd/Open-Platypus", None, "train", 1 * GB),
    ("aya_redteam", "CohereForAI/aya_redteaming", None, "train", 1 * GB),
]


def turns_from_list(v):
    """Any list-of-dicts (content/value/utterance/text + role/from/
    speaker) or list-of-str (alternating user/assistant) -> text."""
    if not isinstance(v, list) or not v:
        return None
    if all(isinstance(x, str) for x in v):
        lines = [x for x in v if x.strip()]
        parts = ["Human: %s" % x[:800] if i % 2 == 0
                 else "Assistant: %s" % x[:800]
                 for i, x in enumerate(lines)]
        return "\n".join(parts)[:6000] or None
    if all(isinstance(x, dict) for x in v):
        parts = []
        for i, m in enumerate(v):
            c = m.get("content", m.get("value", m.get("utterance",
                      m.get("text", ""))))
            r = m.get("role", m.get("from", m.get("speaker",
                      m.get("author", ""))))
            if not r:
                r = "Human" if i % 2 == 0 else "Assistant"
            if c:
                parts.append("%s: %s" % (r, str(c)[:800]))
        return "\n".join(parts)[:6000] or None
    return None


def extract(ex):
    """Cascade over known dialogue/text schemas -> plain text or None."""
    if isinstance(ex, dict):
        if "human_ref_A" in ex:
            try:
                win = ("human_ref_A"
                       if float(ex.get("score_A", 0))
                       >= float(ex.get("score_B", 0))
                       else "human_ref_B")
            except Exception:
                win = "human_ref_A"
            h, r = str(ex.get("history", ""))[:1500], str(ex.get(win, ""))
            if h or r:
                return "Human: %s\nAssistant: %s" % (h, r[:2500])
        for qk in ("prompt", "instruction", "question", "query"):
            for rk in ("response", "output", "answer", "chosen",
                       "completion"):
                q, r = ex.get(qk, ""), ex.get(rk, "")
                if isinstance(q, str) and isinstance(r, str) and (q or r):
                    if isinstance(ex.get(rk), list):
                        r = " ".join(map(str, ex[rk]))
                    return "Human: %s\nAssistant: %s" % (q[:2000], r[:3000])
        for key in ("messages", "conversations", "conversation", "dialogue",
                    "dialog", "turns", "utterances", "history", "thread"):
            t = turns_from_list(ex.get(key))
            if t:
                return t
        if isinstance(ex.get("context"), list) and ex.get("response"):
            pre = turns_from_list(ex["context"]) or ""
            return (pre + "\nAssistant: %s"
                    % str(ex["response"])[:2500]).strip() or None
        for key in ("text", "content", "chosen", "prompt"):
            v = ex.get(key)
            if isinstance(v, str) and len(v) > 50:
                return v[:6000]
        q, r = ex.get("question", ""), ex.get("response", "")
        if q or r:
            return "Human: %s\nAssistant: %s" % (q[:1500], r[:1500])
    return None


def row_count(path):
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def fetch_one(tag, hf_id, config, split, cap):
    from datasets import load_dataset
    path = os.path.join(OUTDIR, "%s.jsonl" % tag)
    done = row_count(path)
    if os.path.exists(path) and os.path.getsize(path) >= cap * 0.9:
        return {"status": "exists", "bytes": os.path.getsize(path)}
    ds = load_dataset(hf_id, config, split=split, streaming=True,
                      trust_remote_code=False)
    if done:
        ds = ds.skip(done)  # resume partials, don't restart
    nbytes = os.path.getsize(path) if done else 0
    nrows = done
    mode = "a" if done else "w"
    with open(path, mode, encoding="utf-8") as f:
        for ex in ds:
            t = extract(ex)
            if not t:
                continue
            line = json.dumps({"text": t, "source": tag}) + "\n"
            f.write(line)
            nbytes += len(line.encode("utf-8", errors="ignore"))
            nrows += 1
            if nbytes >= cap:
                break
    return {"status": "ok" + (" (resumed)" if done else ""),
            "bytes": nbytes, "rows": nrows}


def main():
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
        if a.startswith("--outdir="):
            global OUTDIR
            OUTDIR = a.split("=", 1)[1]
    os.makedirs(OUTDIR, exist_ok=True)
    rep_path = os.path.join(OUTDIR, "fetch_report.json")
    rep = {}
    if os.path.exists(rep_path):
        try:
            rep = json.load(open(rep_path, encoding="utf-8"))
        except Exception:
            rep = {}
    for tag, hf_id, config, split, cap in SOURCES:
        if only and tag != only:
            continue
        try:
            r = fetch_one(tag, hf_id, config, split, cap)
        except Exception as e:
            r = {"status": "SKIP: %s: %s" % (type(e).__name__,
                                             str(e)[:120])}
        rep[tag] = r
        print("[fetch] %s: %s" % (tag, r), flush=True)
    json.dump(rep, open(rep_path, "w"), indent=1)
    return rep


if __name__ == "__main__":
    main()
