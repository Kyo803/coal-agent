import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:1234/v1"


def models():
    with urllib.request.urlopen(BASE + "/models", timeout=10) as r:
        d = json.loads(r.read().decode())
        items = d.get("data") or d.get("models") or []
        return items[0].get("id") if items else None


def bench(n_predict=160, prompt="Write a short Python function that merges two sorted lists."):
    mid = models()
    body = {
        "model": mid or "local",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": n_predict,
        "temperature": 0.2,
        "stream": False,
    }
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read().decode())
    dt = time.time() - t0
    usage = out.get("usage", {})
    ct = usage.get("completion_tokens", 0)
    tps = ct / dt if dt else 0
    print(json.dumps({"model": mid, "completion_tokens": ct,
                      "seconds": round(dt, 2), "tok_per_s": round(tps, 2)}))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 160
    bench(n)