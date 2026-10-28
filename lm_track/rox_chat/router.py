"""ROX N task router + thinking controller.

Decides, per message, which model and whether to enable reasoning:
  simple   -> fast path (small model, no thinking)
  reasoning-> big model + thinking ON (hard questions)
  coding   -> big model (thinking optional)
  vision   -> big model with images

Defaults route everything to the 35B (the user's choice); the fast path
is only used when explicitly enabled, so quality is never sacrificed
silently.

  from router import route
  r = route("debug this segfault in my C code")
  r["model"], r["thinking"], r["kind"]
"""
import re

from rox_config import cfg

CODE_HINTS = ["def ", "class ", "function", "```", "import ", "traceback",
              "segfault", "compile", "error:", "stack trace", "api",
              "regex", "sql", "bash", "powershell", "refactor", "debug",
              "implement", "algorithm", "complexity", "bug"]
REASON_HINTS = ["why", "explain", "prove", "derive", "analyze", "compare",
                "step by step", "reason", "calculate", "solve", "design",
                "trade-off", "tradeoff", "evaluate", "strategy", "plan"]
SIMPLE_HINTS = ["hi", "hello", "hey", "thanks", "thank you", "how are you",
                "good morning", "good night", "bye", "ok", "okay"]


def classify(text, has_image=False):
    if has_image:
        return "vision"
    t = (text or "").lower().strip()
    if len(t) <= 24 and any(t.startswith(h) or t == h for h in SIMPLE_HINTS):
        return "simple"
    if any(h in t for h in CODE_HINTS) or "```" in text:
        return "coding"
    if any(h in t for h in REASON_HINTS) or len(t.split()) > 40:
        return "reasoning"
    if re.search(r"\d\s*[\+\-\*/]\s*\d", t):
        return "arithmetic"
    return "chat"


def route(text, has_image=False, prefer_fast=False):
    """Return {kind, model, base_url, thinking}."""
    kind = classify(text, has_image)
    big_model = os.path.basename(cfg.model_path() or "model")
    big_url = cfg.base_url
    fast = (cfg.get("fallback_servers") or [None])[0]

    # When the big model is disabled (ROX_NO_35B=1 — it does not fit in RAM
    # beside the user's work), always use the small local fallback.
    use_fast = (prefer_fast and kind in ("simple", "chat") and fast) or \
        (bool(fast) and bool(os.environ.get("ROX_NO_35B")))
    if use_fast:
        return {"kind": kind, "model": fast["model"],
                "base_url": fast["url"], "thinking": False}

    # thinking: always on if configured (needed so the board can record
    # "what ROX N thought"); otherwise only for reasoning turns.
    thinking = bool(cfg.model.get("thinking", False)) or \
        kind in ("reasoning",)
    return {"kind": kind, "model": big_model, "base_url": big_url,
            "thinking": thinking}


def needs_tools(text):
    """Heuristic: should the model be given memory/document tools?"""
    t = (text or "").lower()
    triggers = ["remember", "my ", "i am", "i'm", "we ", "our ", "project",
                "document", "file", "code", "last time", "earlier",
                "previously", "recall", "forget", "note that"]
    return any(h in t for h in triggers)


import os  # noqa: E402  (after use in route for basename)


if __name__ == "__main__":
    for q in ["hey there", "explain why TCP needs a handshake",
              "debug this python traceback", "what is 12*9",
              "remember that I use NEMA 23 motors"]:
        r = route(q)
        print(f"{q[:42]:44s} -> kind={r['kind']:10s} "
              f"thinking={r['thinking']} tools={needs_tools(q)}")
