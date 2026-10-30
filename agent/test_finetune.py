"""Tests for the fine-tune hook (offline; no training)."""
import os
import tempfile

PASS = FAIL = 0


def ok(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")


def main():
    from learning import notes
    from finetune import tune, cookbook, dataset

    print("== 1. dataset from notes ==")
    notes.add("finetune_topic",
              "Hash tables map keys to buckets via a hash function and "
              "resolve collisions with chaining or open addressing.")
    notes.add("finetune_topic",
              "Load factor above ~0.75 should trigger a resize and rehash "
              "to keep operations near O(1).")
    data = dataset.build(limit=50)
    ok("built pairs", len(data) >= 2)
    ok("chat format",
       all(set(d["messages"][0]) == {"role", "content"} for d in data))
    ok("has assistant turn",
       all(d["messages"][-1]["role"] == "assistant" for d in data))

    print("== 2. dedupe ==")
    d1 = dataset.build(limit=50)
    keys = [d["messages"][-1]["content"][:200] for d in d1]
    ok("no duplicate assistant content", len(keys) == len(set(keys)))

    print("== 3. cookbook ==")
    script = cookbook.train_script()
    ok("script uses peft/QLoRA", "peft" in script and "BitsAndBytes" in script)
    ok("script binds BASE path", "BASE = r" in script)
    book = cookbook.runbook()
    ok("runbook mentions QLoRA", "QLoRA" in book)

    print("== 4. plan/estimate ==")
    est = tune.estimate(200)
    ok("estimate has cost", "cost_usd" in est and len(est["cost_usd"]) == 2)
    ok("gpu_hours > 0", est["gpu_hours"] > 0)
    p = tune.plan()
    ok("plan has base model", bool(p["base_model"]))

    print("== 5. export bundle ==")
    tmp = tempfile.mkdtemp()
    man = tune.export(tmp)
    ok("dataset written", os.path.exists(os.path.join(tmp, "dataset.jsonl")))
    ok("script written", os.path.exists(os.path.join(tmp, "train_qlora.py")))
    ok("runbook written", os.path.exists(os.path.join(tmp, "RUNBOOK.md")))
    ok("manifest examples", man["examples"] >= 2)

    print("=" * 40)
    print(f"{PASS} passed, {FAIL} failed")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(0 if main() == 0 else 1)
