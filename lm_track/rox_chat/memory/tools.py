"""Model-callable memory tools. The model learns (in SFT) to emit these
as special tokens; the runtime executes them and feeds results back.

Tool call format (trained):
  <|tools|>search_memory: my dog<|tools|>
  <|tools|>remember: my robot arm uses NEMA 23<|tools|>
  <|tools|>update_profile: style=concise<|tools|>
  <|tools|>forget: old address<|tools|>
"""
import re

TOOL_RE = re.compile(r"<\|tools\|>\s*([a-z_]+)\s*:\s*(.*?)\s*<\|tools\|>",
                     re.S)


class MemoryTools:
    def __init__(self, memory):
        self.mem = memory

    def execute(self, name, arg):
        name = name.strip().lower()
        if name == "search_memory":
            hits = self.mem.search(arg, k=5)
            if not hits:
                return "no memories found"
            return "\n".join(f"- ({h['role']}) {h['text'][:200]}"
                             for h in hits)
        if name == "remember":
            self.mem.remember(arg, kind="fact")
            return f"stored: {arg[:80]}"
        if name == "update_profile":
            if "=" in arg:
                k, v = arg.split("=", 1)
                self.mem.profile.set(k.strip(), v.strip())
                return f"profile.{k.strip()} = {v.strip()}"
            return "usage: key=value"
        if name == "forget":
            return self._forget(arg)
        return f"unknown tool: {name}"

    def _forget(self, query):
        """Privacy deletion: mark matching messages as forgotten."""
        hits = self.mem.search(query, k=20)
        removed = 0
        for h in hits:
            self.mem.store.conn.execute(
                "UPDATE messages SET text='[forgotten]' WHERE id=?",
                (h["id"],))
            removed += 1
        self.mem.store.conn.commit()
        return f"forgot {removed} matching memories"

    def parse_and_run(self, text):
        """Find all tool calls in model output, execute, return
        (cleaned_text, results)."""
        results = []
        for m in TOOL_RE.finditer(text):
            results.append((m.group(1), m.group(2),
                            self.execute(m.group(1), m.group(2))))
        cleaned = TOOL_RE.sub("", text).strip()
        return cleaned, results


def format_tool_results(results):
    if not results:
        return ""
    parts = []
    for name, arg, out in results:
        parts.append(f"[{name}: {arg[:60]}] -> {out}")
    return "\n".join(parts)


if __name__ == "__main__":
    class _FakeMem:
        def search(self, q, k=5):
            return [{"id": 1, "role": "user", "text": "my dog is Biscuit"}]

        def remember(self, t, kind="fact"):
            return 1
    from types import SimpleNamespace
    mem = _FakeMem()
    mem.profile = SimpleNamespace(set=lambda k, v: None)
    mem.store = SimpleNamespace(conn=SimpleNamespace(
        execute=lambda *a: None, commit=lambda: None))
    t = MemoryTools(mem)
    txt = 'Sure. <|tools|>search_memory: my dog<|tools|> Done.'
    cleaned, res = t.parse_and_run(txt)
    print("[tools] cleaned:", repr(cleaned))
    print("[tools] result:", format_tool_results(res))
