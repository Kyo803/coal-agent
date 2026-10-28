import sys
sys.path.insert(0, ".")
from tools.intent import detect_intent
for q in ["rewrite the file called service.py so it is correct",
          "rewrite service.py with a correct implementation",
          "make a file called service.py that is correct"]:
    i = detect_intent(q)
    print(f"{q[:48]:50s} -> {i.tool} [{i.confidence}] path={i.args.get('path')}")