import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coal import Coal

r = Coal(session_name="_g5", auto_start=True)
r._auto_approve = True
p = r._open_project("arcade-frontend")
r.project = p
b = r._gen_file(
    'Rewrite the ENTIRE file "src/main.tsx" for this project. Write the '
    "COMPLETE file body inside one code block. Output only the code, "
    "never the filename.", "src/main.tsx")
print("LEN", len(b))
print("REPR:", repr(b))
r.close()