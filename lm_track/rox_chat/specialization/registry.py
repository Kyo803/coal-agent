"""Task-Specialization Router: pick the brain configuration for a task.

Each family yields: a serving profile (measured-best on this rig =
'chat'), a domain system-prompt overlay, a verifier mode, and context
boost. This is what makes ROX N 'greater' at each specific hard task.
"""
from __future__ import annotations

OVERLAYS = {
    "chip": (
        "You are ROX N Silicon Lab, engineering digital RTL. Write "
        "synchronous Verilog that exactly matches the declared module "
        "interface. Use non-blocking assignments in clocked blocks. "
        "Provide a testbench that prints <MODULE>:PASS only when results "
        "are correct and calls $fatal otherwise. Keep modules small and "
        "composable."
    ),
    "code": (
        "You build real, runnable software: prefer small correct files, "
        "package/build scripts that actually run, and exact expected "
        "interfaces between modules."
    ),
    "long_doc": (
        "Handle very long inputs: extract structure, key claims and "
        "sources; compress, never invent."
    ),
    "chat": "",
}

FAMILIES = {
    "chip": {
        "keywords": ["verilog", "hdl", "rtl", "fpga", "chip", "alu", "ram",
                     "rom", "cpu", "testbench", "vga", "gpu", "fifo", "soc",
                     "combinational", "fsm", "synthesi"],
        "mode": "hdl_gates", "server_profile": "chat",
        "context_boost": 0, "overlay": OVERLAYS["chip"]},
    "code": {
        "keywords": ["python", "typescript", "javascript", "node", "react",
                     "build", "compile", "function", "class", "package",
                     "npm", "pip", "git clone"],
        "mode": "builder_gates", "server_profile": "chat",
        "context_boost": 0, "overlay": OVERLAYS["code"]},
    "long_doc": {
        "keywords": ["summarize", "document", "long", "book", "research",
                     "notes", "chapter", "report"],
        "mode": "rag", "server_profile": "chat",
        "context_boost": 1, "overlay": OVERLAYS["long_doc"]},
    "chat": {
        "keywords": [], "mode": "chat", "server_profile": "chat",
        "context_boost": 0, "overlay": OVERLAYS["chat"]},
}

FAMILY_ORDER = ["chip", "code", "long_doc"]


def classify(text: str) -> str:
    t = (text or "").lower()
    for fam in FAMILY_ORDER:
        for kw in FAMILIES[fam]["keywords"]:
            if kw in t:
                return fam
    return "chat"


def route(text: str) -> dict:
    fam = classify(text)
    f = FAMILIES[fam]
    return {"family": fam, "profile": f["server_profile"],
            "mode": f["mode"], "overlay": f["overlay"],
            "context_boost": f["context_boost"]}
