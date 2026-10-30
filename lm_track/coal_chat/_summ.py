import json
import os

p = os.path.expanduser(r"~\.coal\work\sec_test\battery.json")
for x in json.load(open(p, encoding="utf-8")):
    ans = (x["answer"] or "(none)").replace("\n", " ")
    print(f"{x['case']:8s} tools={x['tools']} {x['wall_s']}s "
          f"chars={len(x['answer'])}")
    print("   ", ans[:150])
