"""Compare candidate STR triggers: which signal best predicts WRONGNESS?

Metrics per signal: AUROC for P(wrong | signal), plus an operating table
(trigger rate vs precision/recall at fixed thresholds). Combined trigger:
retrieve iff (min_prob below thr) OR (samples disagree) — the two-stage
design from trigger_spec.md.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def auroc(scores, labels):
    # labels: 1 = wrong (event to detect). Rank-based, no sklearn needed.
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0] * len(scores)
    for r, i in enumerate(order, start=1):
        ranks[i] = r
    n1 = sum(labels)
    n0 = len(labels) - n1
    if not n1 or not n0:
        return float("nan")
    s = sum(ranks[i] for i in range(len(scores)) if labels[i])
    return (s - n1 * (n1 + 1) / 2) / (n1 * n0)


def opoint(rows, pred):
    tp = sum(1 for r, p in zip(rows, pred) if p and not r["correct"])
    fp = sum(1 for r, p in zip(rows, pred) if p and r["correct"])
    fn = sum(1 for r, p in zip(rows, pred) if not p and not r["correct"])
    rate = sum(pred) / len(pred)
    return {"rate": round(rate, 3),
            "prec": round(tp / max(1, tp + fp), 3),
            "rec": round(tp / max(1, tp + fn), 3)}


def main():
    d = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
    rows = d["rows"]
    wrong = [0 if r["correct"] else 1 for r in rows]
    print(f"model={d['model']} acc={d['accuracy']:.2f} n={len(rows)} "
          f"wrong={sum(wrong)}")
    sigs = {
        # higher score = more likely wrong
        "min_prob(low)": [-r["min_prob"] for r in rows],
        "neg_logprob": [-r["mean_logprob"] for r in rows],
        "disagree": [r["disagree"] for r in rows],
        "input_novelty(-q_fam)": [-r["q_fam"] for r in rows],
    }
    for name, s in sigs.items():
        print(f"AUROC(wrong | {name:14s}) = {auroc(s, wrong):.3f}")
    print("\nOperating points (retrieve = predicted wrong):")
    for thr in (0.5, 0.7, 0.9):
        p = [r["min_prob"] < thr for r in rows]
        print(f"  min_prob<{thr}: {opoint(rows, p)}")
    for thr in (0.25, 0.5):
        p = [r["disagree"] >= thr for r in rows]
        print(f"  disagree>={thr}: {opoint(rows, p)}")
    p = [(r["min_prob"] < 0.7) or (r["disagree"] >= 0.5) for r in rows]
    print(f"  COMBINED (minp<0.7 OR dis>=0.5): {opoint(rows, p)}")
    # The key diagnostic for the S_t critique: wrong answers the model
    # states confidently (high min_prob AND full agreement).
    silent = [r for r in rows if not r["correct"] and r["min_prob"] >= 0.7
              and r["disagree"] == 0.0]
    print(f"\nconfident-and-wrong (minp>=0.7, full agreement): {len(silent)} "
          f"of {sum(wrong)} wrong — no single-pass OR consistency trigger "
          f"can catch these (systematic error, needs retrieval-always "
          f"domains or training fixes, not a better threshold).")
    for r in silent[:6]:
        print(f"  - {r['q'][:50]} -> {r['out'][:40]!r}")
    # Direct S_t analog test: wrong answers on HIGH-familiarity inputs
    # (model finds the question unsurprising yet answers wrongly).
    import statistics
    med = statistics.median(r["q_fam"] for r in rows)
    miss = [r for r in rows if not r["correct"] and r["q_fam"] >= med]
    print(f"\nwrong-on-familiar-input (q_fam >= median {med:.2f}): "
          f"{len(miss)} of {sum(wrong)} wrong — an input-novelty trigger "
          f"at median threshold misses all of these; output-side signals "
          f"must carry the decision.")


if __name__ == "__main__":
    main()
