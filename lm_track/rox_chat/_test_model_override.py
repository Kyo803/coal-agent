"""Confirm the local-model-name override against a remote endpoint."""
import os

from streaming import stream_chat

base = "https://api.studio.nebius.com/v1"
print("ROX_AGENT_MODEL:", os.environ.get("ROX_AGENT_MODEL"))
for m in ["qwen2.5:3b", None, "nvidia/nemotron-3-super-120b-a12b"]:
    try:
        text, tools, reason = stream_chat(
            [{"role": "user", "content": "Reply with exactly: OK"}],
            model=m, base_url=base, max_tokens=64)
        print(f"model={m!r:40s} -> {text[:60]!r}")
    except Exception as e:
        print(f"model={m!r:40s} -> EXC {type(e).__name__}: {e}")
