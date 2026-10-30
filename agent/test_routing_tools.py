"""Routing regression: a domain request must expose that domain's tools.

This is the bug class that made chip builds and security questions fall
through to generic shell/file tools: the category existed but nothing
triggered it, or the tool cap truncated it away.
"""
import sys

from tools.exec import lazy_schemas
from tools.permissions import Permissions
from tools.specs import categories_for_trigger

PASS = FAIL = 0


def ok(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")


def names(prompt):
    return [s["function"]["name"]
            for s in (lazy_schemas(prompt, Permissions()) or [])]


CASES = [
    ("build a 12-bit up counter chip", "chip", "chip_build"),
    ("build a 4-bit gray to binary converter chip", "chip", "chip_build"),
    ("plan a chip design for me", "chip", "chip_build"),
    ("show me the die map of the chip", "chip", "chip_views"),
    ("test my site for SQL injection (I own it)", "security",
     "security_kb"),
    ("explain XSS and how to prevent it", "security", "security_kb"),
    ("analyse this binary for suspicious strings", "security", "sast_check"),
    ("explain stack buffer overflows in assembly", "security",
     "security_method"),
    ("triage a suspected malware infection", "security", "security_kb"),
]

print("== domain prompts expose their tools ==")
for prompt, cat, tool in CASES:
    cats = categories_for_trigger(prompt)
    ns = names(prompt)
    ok(f"{prompt[:40]:42s} -> {cat} + {tool}",
       cat in cats and tool in ns)

print("== plain requests do not ==")
for prompt in ("what is 12 + 5", "write a haiku about the sea"):
    cats = categories_for_trigger(prompt)
    ok(f"{prompt[:40]:42s} -> no chip/security",
       "chip" not in cats and "security" not in cats)

print("== web requests must be able to write files ==")
for prompt in (
    r"Create a small website in C:\x\site using write_file: index.html "
    "and a click counter in app.js",
    "Create an Amazon-like storefront called Nile with a cart",
):
    cats = categories_for_trigger(prompt)
    ns = names(prompt)
    ok(f"{prompt[:40]:42s} -> write_file + no chip",
       "write_file" in ns and "chip" not in cats)

print("== forced intents cannot be hijacked by one keyword ==")
from tools.intent import detect_intent, plausible_intent
HIJACK = [
    (r"Create a website in C:\x with app.js (a click counter)", "chip_build"),
    ("Create an Amazon-like storefront called Nile", "remember"),
]
for prompt, bad in HIJACK:
    it = detect_intent(prompt)
    ok(f"{prompt[:40]:42s} -> does not force {bad}",
       not (it.tool == bad and plausible_intent(bad, prompt)))
ok("a real chip request still forces chip_build",
   plausible_intent("chip_build", "build a 4-bit counter chip"))
ok("a real memory request still forces remember",
   plausible_intent("remember", "remember that I use 24 GB of RAM"))
ok("an explicit path is not turned into a new project",
   not plausible_intent("build_project",
                        r"create a site in C:\x\site"))

print("== missing required arguments are rejected ==")
from tools.exec import ToolExecutor
res = ToolExecutor().run("write_file", {"content": "x"})
ok("write_file without a path is rejected",
   res.get("ok") is False and "missing required" in res.get("output", ""))

print("== executables stay confirm-tier ==")
from tools import specs as S
for name in ("run_command", "write_file", "open_app", "chip_build"):
    spec = S.get(name)
    print(f"  {name:14s} tier={spec['tier']}")
ok("execution/write/open need approval",
   all(S.get(n)["tier"] == "confirm"
       for n in ("run_command", "write_file", "open_app")))
ok("chip_build runs without an approval prompt",
   S.get("chip_build")["tier"] != "confirm")

print("=" * 40)
print(f"{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
