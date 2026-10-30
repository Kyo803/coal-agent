"""Metrics for the Coal evaluation suite. No external deps."""


def acc(correct, total):
    return round(correct / total, 4) if total else 0.0


def precision_recall_f1(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return round(p, 4), round(r, 4), round(f1, 4)


def confusion(preds, golds):
    tp = sum(1 for p, g in zip(preds, golds) if p and g)
    fp = sum(1 for p, g in zip(preds, golds) if p and not g)
    fn = sum(1 for p, g in zip(preds, golds) if not p and g)
    tn = sum(1 for p, g in zip(preds, golds) if not p and not g)
    return tp, fp, fn, tn


def summarize(results):
    """results: {name: {metric: value, ...}} -> compact dict."""
    out = {}
    for name, r in results.items():
        out[name] = {k: v for k, v in r.items()
                     if isinstance(v, (int, float, str))}
    return out
