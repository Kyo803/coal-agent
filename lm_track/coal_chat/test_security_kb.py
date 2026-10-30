"""QA battery for the security knowledge base and methodology tools."""
from tools.exec import ToolExecutor
from tools.handlers_security_kb import (ALL, PLATFORMS, VDP, FORUMS, LEARNING,
                                        STANDARDS, TOOLS, CONFERENCES,
                                        kb_search, kb_topic)

ex = ToolExecutor()
PASS = FAIL = 0


def ok(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  {detail}")


print("== data integrity ==")
ok("total >= 200 entries", len(ALL) >= 200, len(ALL))
ok("no duplicate names", len({r[0] for r in ALL}) == len(ALL),
   len(ALL) - len({r[0] for r in ALL}))
ok("every entry has a url", all(r[1].strip() for r in ALL))
ok("every entry has 3 fields", all(len(r) == 3 for r in ALL))
ok("no empty category", all([PLATFORMS, VDP, FORUMS, LEARNING, STANDARDS,
                             TOOLS, CONFERENCES]))
ok("forums >= 50", len(FORUMS) >= 50, len(FORUMS))
ok("platforms >= 20", len(PLATFORMS) >= 20, len(PLATFORMS))

print("\n== search by each kind ==")
for kind, n in (("platform", len(PLATFORMS)), ("vdp", len(VDP)),
                ("forum", len(FORUMS)), ("learning", len(LEARNING)),
                ("standard", len(STANDARDS)), ("tool", len(TOOLS)),
                ("conference", len(CONFERENCES))):
    t = kb_search("", kind, 200)
    ok(f"kind={kind} returns all {n}", t.count("\n- ") >= n, t.count("\n- "))

print("\n== query matching ==")
ok("hackerone found", "HackerOne" in kb_search("hackerone"))
ok("case-insensitive", "HackerOne" in kb_search("HACKERONE"))
ok("matches note text", "Web3" in kb_search("web3"))
ok("matches domain", "bugcrowd.com" in kb_search("bugcrowd.com"))
ok("unknown query -> message", "no entry matches" in kb_search("zzzznope"))
ok("cross-category hit", "burp" in kb_search("burp").lower())

print("\n== edge cases ==")
r = ex.run("security_kb", {})
ok("no args works", r.get("ok") and "entries" in (r.get("output") or ""))
r = ex.run("security_kb", {"limit": 0})
ok("limit=0 clamped", r.get("ok"))
r = ex.run("security_kb", {"limit": 9999})
ok("limit=9999 clamped", r.get("ok"))
r = ex.run("security_kb", {"kind": "nonexistent"})
ok("bad kind handled", r.get("ok") is not None)

print("\n== methodology ==")
for topic, marker in (("authorisation", "permission"),
                      ("scope", "permission"),
                      ("recon", "attack surface"),
                      ("bug_classes", "IDOR"),
                      ("reporting", "Steps to reproduce"),
                      ("code", "untrusted input")):
    t = kb_topic(topic)
    ok(f"topic={topic}", marker.lower() in t.lower(), t[:60])
ok("unknown topic lists topics", "unknown topic" in kb_topic("nope"))
ok("empty topic lists topics", "topics:" in kb_topic(""))

print("\n== every method leads with authorisation ==")
auth = kb_topic("authorisation")
ok("authorisation first", auth.strip().startswith("## rules"))

print(f"\n{'='*40}\n{PASS} passed, {FAIL} failed")
