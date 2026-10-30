import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coal import Coal

name = sys.argv[1] if len(sys.argv) > 1 else "arcade-frontend"
r = Coal(session_name="_repair", auto_start=True)
r._auto_approve = True
p = r._open_project(name)
log = []
ok = r._verify_and_repair(p, "npm run build", log)
print("\n".join(log))
print("VERIFY:", "PASSED" if ok else "FAILED")
r.close()