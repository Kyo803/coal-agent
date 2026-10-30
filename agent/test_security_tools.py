"""Security tooling: scanners must find real issues, triage must parse PE."""
import os
import sys
import tempfile

from tools.exec import ToolExecutor

PASS = FAIL = 0
ex = ToolExecutor()


def ok(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} {detail}")


tmp = tempfile.mkdtemp(prefix="coal_sec_")

# --- SAST finds a real C buffer overflow -------------------------------
src = os.path.join(tmp, "bad.c")
with open(src, "w", encoding="utf-8") as f:
    f.write('#include <string.h>\nvoid g(char *n){ char b[8]; strcpy(b, n); }\n')
r = ex.run("sast_check", {"path": tmp})
out = r.get("output") or ""
ok("sast_check flags strcpy", r.get("ok") and "unsafe_c_string" in out, out[:120])
ok("sast_check cites the file", "bad.c" in out)

# --- secret scan finds an AWS key -------------------------------------
sec = os.path.join(tmp, "conf.py")
with open(sec, "w", encoding="utf-8") as f:
    f.write('AWS_KEY = "AKIA' + "A" * 16 + '"\n')
r = ex.run("scan_secrets", {"path": tmp})
ok("scan_secrets flags an AWS key",
   r.get("ok") and "aws_access_key" in (r.get("output") or ""),
   (r.get("output") or "")[:120])

# --- log parsing ------------------------------------------------------
log = os.path.join(tmp, "access.log")
with open(log, "w", encoding="utf-8") as f:
    f.write('1.2.3.4 - - [10/Oct/2026:13:55:36 +0000] "GET /a HTTP/1.1" '
            '200 123\n')
r = ex.run("parse_logs", {"path": log})
ok("parse_logs parses a CLF line",
   r.get("ok") and "1.2.3.4" in (r.get("output") or ""),
   (r.get("output") or "")[:160])

# --- binary triage on the running interpreter (a real PE) --------------
r = ex.run("binary_triage", {"path": sys.executable})
out = r.get("output") or ""
ok("binary_triage identifies a PE", "format    : PE" in out, out[:120])
ok("binary_triage hashes the file",
   len(r.get("sha256") or "") == 64)
ok("binary_triage lists sections", "section   :" in out)
ok("binary_triage does not execute the sample",
   "NOT executed" in out)

# --- a non-binary path is rejected cleanly ----------------------------
r = ex.run("binary_triage", {"path": os.path.join(tmp, "nope.bin")})
ok("missing file rejected", r.get("ok") is False)

print("=" * 40)
print(f"{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
