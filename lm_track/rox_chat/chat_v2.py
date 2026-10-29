"""ROX N v2 chat: memory-wired conversation with all inference features.

Per turn:
  1. safety backstop (thin) + learned behavior from the model
  2. assemble context from 5-tier memory (core/facts/episodic/working)
  3. tool short-circuits (calculator) when the question is arithmetic
  4. generate
  5. parse+run model memory-tool calls
  6. store turn, consolidate every N turns

  python chat_v2.py --model rox_500m_v2.pt
  python chat_v2.py --backend hf            # fallback to HF model now
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class RoxV2:
    def __init__(self, model_path=None, backend="v2", mem_root="~/.rox",
                 tokenizer=None, qwen_url=None, qwen_model=None):
        self.backend = backend
        from memory import Memory
        self.mem = Memory(mem_root)
        from memory.tools import MemoryTools, format_tool_results
        self.tools = MemoryTools(self.mem)
        self.format_tools = format_tool_results
        self.turn_count = 0
        self.model = None
        self.tok = None
        self.qwen = None
        if backend == "qwen":
            from qwen_backend import QwenBackend
            url = (qwen_url or os.environ.get("ROX_AGENT_URL")
                   or "http://localhost:1234/v1")
            local = ("localhost" in url) or ("127.0.0.1" in url)
            key = (""
                   if local else os.environ.get("NEBIUS_API_KEY", ""))
            mdl = (qwen_model or os.environ.get("ROX_AGENT_MODEL")
                   or ("qwen3.6-35b-a3b" if local
                       else "nvidia/nemotron-3-super-120b-a12b"))
            self.qwen = QwenBackend(
                base_url=url, model=mdl, api_key=key,
                reasoning_effort=None if local else "none")
            if not self.qwen.health():
                print("[chat_v2] WARNING: model server not reachable at "
                      f"{self.qwen.base_url} — start it to chat.")
        elif backend == "v2" and model_path and os.path.exists(model_path):
            from local_run import load_model
            self.model, self.cfg = load_model(model_path)
            if tokenizer:
                from tokenizers import ByteLevelBPETokenizer
                self.tok = ByteLevelBPETokenizer(
                    os.path.join(tokenizer, "vocab.json"),
                    os.path.join(tokenizer, "merges.txt"))
        elif backend == "hf":
            from hf_backend import HFDraft
            self.hf = HFDraft()

    # ---- safety (hybrid: learned primary, thin backstop here) ----
    def safety(self, text):
        from attachments import lockout_check
        return lockout_check(text)

    # ---- tool short-circuit ----
    def try_tool(self, text):
        from attachments import tool_gate
        handled, out = tool_gate(text)
        return (handled, out)

    def _generate(self, prompt, memory_text=None):
        if self.backend == "hf":
            # HF instruct models need chat format; memory goes in system.
            msgs = []
            if memory_text:
                msgs.append({"role": "system",
                             "content": "Relevant memory:\n" + memory_text})
            msgs.append({"role": "user", "content": self._last_user})
            self.hf.history = msgs
            txt, minp, _, _ = self.hf.draft_fn(self._last_user)
            return txt
        from local_run import generate
        return generate(self.model, self.tok, prompt)

    def respond(self, user_text):
        self._last_user = user_text
        lo = self.safety(user_text)
        if lo["locked"]:
            self.mem.add_turn("user", user_text, 9.0)
            self.mem.add_turn("assistant", lo["text"], 9.0)
            return lo["text"], "lockout"

        handled, calc = self.try_tool(user_text)
        if handled:
            self.mem.add_turn("user", user_text, 1.0)
            self.mem.add_turn("assistant", calc, 1.0)
            return calc, "calculated"

        # --- Qwen path: direct native memory-tool calling ---
        if self.backend == "qwen":
            ctx = self.mem.assemble(user_text, budget_tokens=1200)
            try:
                text, trace = self.qwen.chat_with_tools(
                    user_text, self.tools, memory_context=ctx["text"])
            except Exception as e:
                text = (f"[local model error: {type(e).__name__}. Is LM "
                        f"Studio's server running?]")
                trace = []
            status = "qwen+tools" if trace else "qwen"
            self.mem.add_turn("user", user_text, 1.0)
            self.mem.add_turn("assistant", text, 1.0)
            self.turn_count += 1
            if self.turn_count % 8 == 0:
                self.mem.consolidate()
            return text, status

        ctx = self.mem.assemble(user_text, budget_tokens=1200)
        prompt = ctx["text"] + "\n\n### assistant\n"
        raw = self._generate(prompt, memory_text=ctx["text"])
        cleaned, results = self.tools.parse_and_run(raw)
        if results:
            tfmt = self.format_tools(results)
            # feed tool output back for a grounded final line
            raw2 = self._generate(
                prompt + cleaned + "\n[tool results]\n" + tfmt +
                "\n### assistant\n")
            cleaned = self.tools.parse_and_run(raw2)[0]

        self.mem.add_turn("user", user_text, 1.0)
        self.mem.add_turn("assistant", cleaned, 1.0)
        self.turn_count += 1
        if self.turn_count % 8 == 0:
            self.mem.consolidate()
        return cleaned, ("tools" if results else "direct")

    def close(self):
        self.mem.consolidate()
        self.mem.store.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--backend", default="qwen",
                    choices=["v2", "hf", "qwen"])
    ap.add_argument("--mem-root", default="~/.rox")
    ap.add_argument("--tokenizer", default=os.path.join(HERE, "tokenizer_v2"))
    ap.add_argument("--qwen-url", default="http://localhost:1234/v1")
    ap.add_argument("--qwen-model", default="qwen3.6-35b-a3b")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    r = RoxV2(args.model, args.backend, args.mem_root, args.tokenizer,
              qwen_url=args.qwen_url, qwen_model=args.qwen_model)
    if args.selftest:
        for u in ["Hi, my name is WERU", "What is 17 times 19?",
                  "what is my name?"]:
            out, status = r.respond(u)
            print(f"you: {u}\nrox [{status}]: {out[:140]}\n")
        r.mem.consolidate()
        print("[chat_v2] selftest OK; memory:", r.mem.store.stats())
        r.mem.store.close()
        return
    print("ROX N v2 ready. 'quit' exits.")
    while True:
        try:
            u = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if u.lower() in ("quit", "exit"):
            break
        if not u:
            continue
        out, status = r.respond(u)
        print(f"rox [{status}]: {out}")
    r.close()


if __name__ == "__main__":
    main()
