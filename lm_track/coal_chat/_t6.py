import json

from selfimprove import experiments

base = open("test_selfimprove.py", encoding="utf-8").read()
benign = {"kind": "code", "target": "test_selfimprove.py",
          "content": base + "\n# benign detail\n"}
marker = 'if __name__ == "__main__":'
idx = base.index(marker)
bad_content = (base[:idx] + "\n\nassert False, 'deliberate regression'\n\n"
               + base[idx:])
bad = {"kind": "code", "target": "test_selfimprove.py",
       "content": bad_content}

rb = experiments.run(benign, suites=["test_selfimprove"])
rbad = experiments.run(bad, suites=["test_selfimprove"])

print("BENIGN passed:", rb["passed"])
print("BAD passed:", rbad["passed"])
print("BAD board failed:", rbad["board"].get("failed"),
      "| rc:", rbad["board"].get("rc"))