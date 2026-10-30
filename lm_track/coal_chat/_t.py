import sys
sys.path.insert(0, ".")
from tools.intent import detect_intent
for q in ["make a file called models.py containing a Python dataclass Task",
          "make a file called storage.py with functions load and save",
          "make a file called service.py that imports Task from models",
          "make me a snake game",
          "make me an image of a dragon"]:
    i = detect_intent(q)
    print(f"{q[:46]:48s} -> {i.tool:14s} path={i.args.get('path')}")