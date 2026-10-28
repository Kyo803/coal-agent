"""Blue-team security tool test suite. Run:  python test_security.py

Deterministic, no model needed: fixtures -> scanners must detect.
"""
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


from tools.handlers_security import (scan_secrets, sast_check, parse_logs,
                                     osint_lookup)

d = tempfile.mkdtemp()
ctx = SimpleNamespace(workspace=d)


def write(name, text):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


print("== 1. scan_secrets ==")
write("creds.txt",
      "AWS key AKIAIOSFODNN7EXAMPLE used here\n"
      "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----\n"
      "token ghp_0123456789abcdef0123456789abcdef012345\n"
      "app_password = 'S3cr3t!LongEnoughValue42'\n")
r = scan_secrets({"path": d}, ctx)
out = r["output"].lower()
check("aws key", "aws_access_key" in out)
check("private key", "private_key" in out)
check("github token", "github_token" in out)
check("high-entropy", "high_entropy_secret" in out)
check("ok flag", r["ok"])

print("== 2. sast_check ==")
write("app.py",
      "import os\n"
      "def run(cmd):\n    return os.system(cmd)\n"
      "def bad():\n    eval(input())\n"
      "def db(q):\n    return cursor.execute(f'SELECT * FROM t WHERE x={q}')\n"
      "pwd = 'hunter2'\n"
      "import hashlib\nmd5 = hashlib.md5(b'x')\n")
r = sast_check({"path": d}, ctx)
out = r["output"].lower()
check("os.system", "os.system" in out)
check("eval", "eval" in out)
check("fstring sql", "fstring_sql" in out)
check("hardcoded pwd", "hardcoded_pwd" in out)
check("weak hash", "weak_hash" in out)

print("== 3. clean code -> no findings ==")
clean = write("clean.py", "def add(a,b):\n    return a+b\n")
r = sast_check({"path": clean}, ctx)
check("clean file no findings", r["output"].split("findings")[0].split(":")[
    1].strip() == "0" or "0 findings" in r["output"])
r = scan_secrets({"path": clean}, ctx)
check("clean file no secrets", "0 findings" in r["output"])

print("== 4. parse_logs ==")
logp = write("access.log",
             '{"ip":"203.0.113.5","method":"GET","path":"/login","status":401}\n'
             '{"ip":"203.0.113.5","method":"POST","path":"/login","status":200}\n'
             '{"ip":"198.51.100.9","method":"GET","path":"/","status":200}\n')
r = parse_logs({"path": logp, "format": "jsonl"}, ctx)
out = r["output"]
check("parses rows", "3 rows" in out, out[:80])
check("ioc surfaced", "203.0.113.5 x2" in out, out[:120])
r2 = parse_logs({"path": logp, "filter": "status=401"}, ctx)
check("filter works", "1 rows" in r2["output"], r2["output"][:80])

print("== 5. osint_lookup (IP, may skip offline) ==")
try:
    r = osint_lookup({"target": "8.8.8.8"}, ctx)
    check("osint ip returns", r["ok"] and r["output"].strip() != "",
          r["output"][:100])
except Exception as e:
    check("osint ip returns", False, f"err {e}")

print("=" * 40)
print(f"{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)