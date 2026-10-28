"""TME turn memory, tool gate, safety lockout (inference attachments).

TME: each completed turn stores (text, S_mean). Over budget: low-S turns
  compress to first-sentence extractive summary; high-S turns kept
  verbatim. Mirrors 'compress stable, preserve change' one level up.
Tool gate: arithmetic/code spans -> sandboxed eval (ast calculator);
  failure -> labeled-estimate path, never silent substitution.
Lockout: small built-in crisis-pattern list (the llm_500m battery is the
  production version; this keeps the interface identical: check()).
"""
import ast
import operator
import re


class TurnMemory:
    def __init__(self, budget_chars=1500, keep_frac=0.3):
        self.turns = []  # (role, text, s_mean)
        self.budget = budget_chars
        self.keep_frac = keep_frac

    def add(self, role, text, s_mean):
        self.turns.append({"role": role, "text": text, "s": float(s_mean)})

    @staticmethod
    def compress(text):
        s = re.split(r"(?<=[.!?])\s+", text.strip())
        return (s[0][:200] + " [compressed]") if s else text[:200]

    def context(self):
        full = sum(len(t["text"]) for t in self.turns)
        if full <= self.budget:
            return [(t["role"], t["text"], False) for t in self.turns]
        scored = sorted(self.turns, key=lambda t: t["s"], reverse=True)
        n_keep = max(1, int(len(scored) * self.keep_frac))
        keep = set(map(id, scored[:n_keep]))
        return [(t["role"], t["text"] if id(t) in keep
                 else self.compress(t["text"]), id(t) not in keep)
                for t in self.turns]

    def recall_probe(self, keyword):
        """Did compression drop a turn containing keyword? Returns it."""
        for t in self.turns:
            if keyword.lower() in t["text"].lower():
                return t["text"]
        return None


OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
       ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.USub: operator.neg,
       ast.Mod: operator.mod}


def safe_calc(expr):
    """Sandboxed arithmetic. Returns (value, verified=True) or raises."""
    tree = ast.parse(expr, mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.operand))
        raise ValueError("not arithmetic")
    return ev(tree), True


ARITH = re.compile(r"(?P<e>\d[\d\s+\-*/%().^]*\d)")


def _norm_ops(text):
    """Normalize spoken arithmetic so the calculator can evaluate it."""
    t = text.replace("^", "**")
    t = re.sub(r"\bmultiplied by\b|\btimes\b", "*", t, flags=re.I)
    t = re.sub(r"\bplus\b|\badded to\b", "+", t, flags=re.I)
    t = re.sub(r"\bminus\b|\bless\b", "-", t, flags=re.I)
    t = re.sub(r"\bdivided by\b|\bover\b", "/", t, flags=re.I)
    t = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", t, flags=re.I)
    return t


def tool_gate(text):
    """Find first arithmetic span; verify by calculator.
    Returns (handled, result_text). Failure -> labeled estimate."""
    t = _norm_ops(text)
    m = ARITH.search(t)
    if not m:
        return False, text
    expr = m.group("e")
    start, end = m.start("e"), m.end("e")
    before = t[start - 1] if start > 0 else ""
    after = t[end] if end < len(t) else ""
    # Ignore digit runs that are part of a path / filename / identifier
    # (e.g. "...\rocket-20261014-161907.obj") — not real arithmetic.
    if before and (before in "\\/._-" or before.isalnum()):
        return False, text
    if after and (after in "\\/._" or after.isalpha()):
        return False, text
    try:
        v, _ = safe_calc(expr)
        # NOTE: prefix taken from normalized t (word-ops replaced), so
        # the shown expression matches what was calculated. Deliberate.
        return True, t[:m.start()] + f"{expr.strip()} = {v} [calculated]"
    except Exception:
        return True, text + " [computation could not be verified — " \
            "treat numbers as an estimate]"


CRISIS = ["kill myself", "kill me", "suicide", "self-harm", "self harm",
          "hurt myself", "cut myself", "hang myself", "end my life",
          "overdose", "want to die", "wanna die", "don't want to live",
          "dont want to live", "no reason to live", "end it all",
          "better off dead"]


SOCIAL = re.compile(
    r"^(hi|hey|hello|yo|oh (really|ok|okay|i see|nice|cool|wow)|thanks|"
    r"thank you|bye|good ?(morning|night|evening)|how are you|lol|haha|"
    r"nice|cool|ok|okay|great|fine|no worries|you too)\b[\s!.?]*$",
    re.IGNORECASE)


def is_social(text):
    """Short social turns carry no factual claim — retrieval must never
    touch them (a greeting answering 'I have no verified information'
    is a routing bug, not honesty). Compound turns ('oh really? how are
    you') count if EVERY sentence-segment is social."""
    t = text.strip()
    if len(t) >= 40:
        return False
    segs = [s for s in re.split(r"[.!?]+", t) if s.strip()]
    return bool(segs) and all(SOCIAL.match(s.strip()) for s in segs)


def lockout_check(text):
    hit = [p for p in CRISIS if p in text.lower()]
    if hit:
        return {"locked": True,
                "text": "I'm concerned about you. Please contact a local "
                        "crisis helpline or emergency services right now. "
                        "I can't help with planning harm.",
                "hits": hit}
    return {"locked": False, "text": text, "hits": []}
