"""Qwen backend: talk to a local LM Studio server (OpenAI-compatible API).

Completely local, no cloud. Default endpoint is LM Studio's local server
(http://localhost:1234/v1). Uses stdlib only (urllib) so there are no new
dependencies. Supports native function calling so Qwen can call ROX N
memory tools directly.

  from qwen_backend import QwenBackend
  b = QwenBackend()
  b.health()                       # -> bool
  out = b.chat([{"role":"user","content":"hi"}])
  out = b.chat_with_tools(text, memory_tools)
"""
import json
import urllib.request
import urllib.error

DEFAULT_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "qwen3.6-35b-a3b"

# Local OpenAI-compatible endpoints, probed in order.
ENDPOINTS = [
    ("http://localhost:1234/v1", "lmstudio"),
    ("http://localhost:11434/v1", "ollama"),
]

# model preference (higher = preferred); matched as substrings
PREFERENCE = [
    "qwen3.6-35b", "qwen3.6-27b", "gemma-4-31b", "gemma-4-26b",
    "qwen3.6", "qwen2.5:7b", "gemma-4-12b", "llama3.1:8b",
    "qwen2.5:3b", "gemma-4-e4b", "llama3.2:3b", "gemma-4-e2b",
]


def _score(model_id):
    m = model_id.lower()
    for i, pref in enumerate(PREFERENCE):
        if pref in m:
            return len(PREFERENCE) - i
    return 0


def autodetect():
    """Return (url, kind, model_id, all_models) for the best live endpoint.
    Prefers LM Studio (larger models) then Ollama; within an endpoint picks
    the highest-preference model."""
    best = (None, None, None, [])
    for url, kind in ENDPOINTS:
        b = QwenBackend(base_url=url)
        if not b.health():
            continue
        models = b.list_models()
        if not models:
            continue
        pick = sorted(models, key=_score, reverse=True)[0]
        if best[2] is None or _score(pick) > _score(best[2]):
            best = (url, kind, pick, models)
    return best

# ROX N memory tools exposed to Qwen as OpenAI-style tool schemas.
MEMORY_TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_memory",
        "description": "Search the user's long-term memory for relevant "
                       "past conversations, facts, projects and preferences.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string",
                      "description": "what to look for"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "remember",
        "description": "Store an important fact about the user for future "
                       "sessions (names, projects, preferences).",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string",
                     "description": "the fact to remember"}},
            "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "update_profile",
        "description": "Update the user's profile (e.g. style=concise, "
                       "name=WERU).",
        "parameters": {"type": "object", "properties": {
            "key": {"type": "string"}, "value": {"type": "string"}},
            "required": ["key", "value"]}}},
    {"type": "function", "function": {
        "name": "forget",
        "description": "Delete matching memories (privacy request).",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}},
            "required": ["query"]}}},
]


class QwenBackend:
    def __init__(self, base_url=DEFAULT_URL, model=DEFAULT_MODEL,
                 temperature=0.7, max_tokens=768, timeout=120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    # ---- low level ----
    def _post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _get(self, path):
        req = urllib.request.Request(self.base_url + path)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    # ---- health ----
    def health(self):
        try:
            d = self._get("/models")
            return bool(d.get("data"))
        except Exception:
            return False

    def list_models(self):
        try:
            return [m.get("id") for m in self._get("/models").get("data", [])]
        except Exception:
            return []

    # ---- chat ----
    def chat(self, messages, tools=None, temperature=None, max_tokens=None,
             no_think=True):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None
            else temperature,
            "max_tokens": self.max_tokens if max_tokens is None
            else max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        # Qwen3.6 supports thinking; disable for fast direct answers.
        if no_think:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        out = self._post("/chat/completions", payload)
        msg = out["choices"][0]["message"]
        return msg

    # ---- chat with memory tools (direct mem call) ----
    def chat_with_tools(self, user_text, memory_tools, memory_context=None,
                        system=None, max_rounds=3):
        """Let Qwen call ROX N memory tools natively, execute them, and
        return the final text plus the tool trace."""
        sys = system or ("You are Rox, a local assistant built in the ROX N "
                         "project. Use memory tools when the user refers to "
                         "past conversations, their projects, or personal "
                         "facts.")
        # Qwen's template allows only ONE system message at the very start,
        # so fold the memory context into it.
        if memory_context:
            sys = sys + "\n\nKnown context:\n" + memory_context
        messages = [{"role": "system", "content": sys}]
        messages.append({"role": "user", "content": user_text})
        trace = []
        for _ in range(max_rounds):
            msg = self.chat(messages, tools=MEMORY_TOOL_SCHEMAS)
            calls = msg.get("tool_calls") or []
            if not calls:
                return msg.get("content", "").strip(), trace
            messages.append(msg)
            for c in calls:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"]["arguments"] or "{}")
                except Exception:
                    args = {}
                if name == "search_memory":
                    result = memory_tools.execute("search_memory",
                                                  args.get("query", ""))
                elif name == "remember":
                    result = memory_tools.execute("remember",
                                                  args.get("text", ""))
                elif name == "update_profile":
                    result = memory_tools.execute(
                        "update_profile",
                        f"{args.get('key','')}={args.get('value','')}")
                elif name == "forget":
                    result = memory_tools.execute("forget",
                                                  args.get("query", ""))
                else:
                    result = f"unknown tool {name}"
                trace.append((name, args, result))
                messages.append({"role": "tool",
                                 "tool_call_id": c.get("id", name),
                                 "content": result})
        # final pass
        msg = self.chat(messages)
        return msg.get("content", "").strip(), trace


if __name__ == "__main__":
    url, kind, model, models = autodetect()
    if url:
        print(f"[qwen] best endpoint: {kind} {url}")
        print(f"[qwen] selected model: {model}")
        print(f"[qwen] all models: {models}")
    else:
        print("[qwen] no local server found. Start LM Studio's server "
              "(port 1234) or Ollama (port 11434).")
