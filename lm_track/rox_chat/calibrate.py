"""STR Calibrator: freeze retrieval thresholds per model scale.

Reads a results.json in str_trigger format (min_prob, disagree, correct
per question), picks theta1 at the cheapest retrieval rate with recall
>= target (default 0.9), plus the disagreement threshold the same way.
Writes frozen config JSON. Re-run per scale — thresholds do not transfer.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def pick(rows, key, direction, recall_target=0.9):
    """direction: 'low' fires when value < thr (min_prob), 'high' when >=."""
    wrong = [not r["correct"] for r in rows]
    nwrong = sum(wrong)
    cands = sorted(set(r[key] for r in rows))
    best = None
    for thr in cands:
        pred = [(r[key] < thr) if direction == "low" else (r[key] >= thr)
                for r in rows]
        tp = sum(1 for w, p in zip(wrong, pred) if w and p)
        rec = tp / max(1, nwrong)
        rate = sum(pred) / len(pred)
        if rec >= recall_target and (best is None or rate < best[1]):
            best = (thr, rate, rec)
    return {"threshold": best[0], "rate": round(best[1], 3),
            "recall": round(best[2], 3)} if best else None


def calibrate(results_path, out_path, recall_target=0.9):
    d = json.load(open(results_path, encoding="utf-8"))
    rows = d["rows"]
    cfg = {
        "model": d.get("model", "?"),
        "n": len(rows),
        "recall_target": recall_target,
        "theta1": pick(rows, "min_prob", "low", recall_target),
        "dis_thr": pick(rows, "disagree", "high", recall_target),
    }
    json.dump(cfg, open(out_path, "w"), indent=1)
    print("[calibrate]", json.dumps(cfg))
    return cfg


if __name__ == "__main__":
    res = os.path.join(HERE, "..", "str_trigger", "results.json")
    out = os.path.join(HERE, "str_config.json")
    for a in sys.argv[1:]:
        if a.startswith("--results="):
            res = a.split("=", 1)[1]
        if a.startswith("--out="):
            out = a.split("=", 1)[1]
    calibrate(res, out)
