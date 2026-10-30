"""Deterministic safety gate for clearly malicious requests.

The model is instructed to refuse malware creation, but instructions alone
are not a control. This gate runs before a mutating tool and blocks the
obvious "write/build me <malware>" requests. Defensive phrasing ("detect",
"analyse", "explain") is explicitly allowed through, so security work is
not crippled.
"""
from __future__ import annotations

import re

_MALWARE = (r"(ransomware|keylogger|credential stealer|stealer|botnet|worm|"
            r"trojan|rootkit|reverse shell|spyware|malware|virus|"
            r"cryptolocker|wiper)")
_MAKE = (r"(write|create|build|make|generate|develop|code|implement|"
         r"produce|program)")
# words that mark legitimate defensive work
_DEFENSIVE = (r"(detect|detector|defend|defense|defence|protect|prevent|"
              r"analyz|analys|analysis|triage|remove|clean|recover|report|"
              r"simulate|sandbox|reverse engineer|understand|explain|"
              r"how does|how do|study|demo|demonstrat)")

_MAKE_MALWARE = re.compile(rf"\b{_MAKE}\b[^.\n]{{0,100}}?\b{_MALWARE}\b",
                           re.I)

_MUTATING = {"write_file", "create_file", "append_file", "run_command",
             "run_script", "shell", "bash", "execute", "sandbox_run",
             "sandbox_write"}


def blocks_tool_for(user_text: str, tool_name: str) -> bool:
    """True when this turn must not run a mutating tool."""
    if tool_name not in _MUTATING:
        return False
    t = user_text or ""
    if re.search(_DEFENSIVE, t, re.I):
        return False
    return bool(_MAKE_MALWARE.search(t))


REFUSAL = (
    "I won't create malware, ransomware, a keylogger, a credential stealer, "
    "or a self-spreading worm. That is outside what Coal will build.\n\n"
    "What I can do instead:\n"
    "- explain how this class of malware works and how it spreads;\n"
    "- write detection logic, YARA/Sigma rules, or a triage checklist;\n"
    "- harden your own app or host against it;\n"
    "- analyse a sample you own in an isolated lab without executing it."
)
