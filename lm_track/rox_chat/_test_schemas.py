import sys
sys.path.insert(0, ".")
from tools.exec import lazy_schemas
from tools.permissions import Permissions
from collections import Counter

p = Permissions()
for q in ["git commit and push", "run pip install numpy",
          "search the web", "write a python script and run it",
          "what is my dogs name", "show files in project"]:
    s = lazy_schemas(q, p)
    names = [x["function"]["name"] for x in s]
    dups = {k: v for k, v in Counter(names).items() if v > 1}
    print(f"{q[:32]:34s} -> {len(s):2d} tools, dups={dups or 'none'}")