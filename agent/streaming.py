"""Streaming client for the local model server (SSE).

Prints tokens as they arrive so a slow 35B reply feels alive instead of
freezing for 40 seconds.

  from streaming import stream_chat
  text = stream_chat(messages, tools=TOOL_SCHEMAS,
                     on_token=lambda t: print(t, end="", flush=True))

Returns the full text plus any tool calls (OpenAI-normalized).
"""
import json
import os
import time
import urllib.request

from coal_config import cfg
from qwen_template import split_thinking, parse_tool_calls


def stream_chat(messages, model=None, base_url=None, tools=None,
                thinking=None, on_token=None, on_thinking=None,
                temperature=None, max_tokens=None, timeout=180,
                tool_choice=None):
    """Stream a chat completion. Returns (content, tool_calls, thinking).

    tool_choice: None/"auto" (let the model choose) or
      {"type": "function", "function": {"name": "write_file"}} to force
      a specific tool call (intent-first path).
    """
    base = (base_url or cfg.base_url).rstrip("/")
    local = ("localhost" in base) or ("127.0.0.1" in base)
    remote_model = os.environ.get("COAL_AGENT_MODEL")
    model = (model or remote_model or "local-model")
    # The router returns LOCAL model names (qwen2.5:3b etc.). Against a hosted
    # endpoint those do not exist, so the call 404s and the answer is empty.
    # Any bare local name is replaced by the configured hosted model.
    if not local and remote_model and "/" not in str(model):
        model = remote_model
    thinking = cfg.model.thinking if thinking is None else thinking
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": cfg.model.temperature if temperature is None
        else temperature,
        "max_tokens": cfg.model.max_tokens if max_tokens is None
        else max_tokens,
    }
    local = ("localhost" in base) or ("127.0.0.1" in base)
    key = "" if local else os.environ.get("NEBIUS_API_KEY", "")
    if os.environ.get("COAL_DEBUG"):
        import sys as _sys
        _sys.stderr.write(
            f"[stream_chat] base={base} model={model} "
            f"key={'yes' if key else 'no'} thinking={thinking}\n")
        _sys.stderr.flush()
    if key:
        # Nemotron-3 is a reasoning model: without this the hidden trace eats
        # the whole token budget and content comes back empty.
        payload["reasoning_effort"] = os.environ.get("COAL_REASONING", "none")
    else:
        payload["chat_template_kwargs"] = {"enable_thinking": bool(thinking)}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"

    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")

    content, tool_calls, reasoning = "", [], ""
    in_think, buf = False, ""
    # COAL_SSE_LOG: append every raw SSE frame with a timestamp. Used to tell
    # a silent provider apart from a stalled client.
    sse_log = os.environ.get("COAL_SSE_LOG")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            if sse_log:
                try:
                    with open(sse_log, "a", encoding="utf-8") as _f:
                        _f.write(f"{time.time():.3f} {raw[:300]!r}\n")
                except Exception:
                    pass
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            choice = (obj.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            piece = delta.get("content") or ""
            # separate <think> from the visible answer
            if piece:
                buf += piece
                while True:
                    if not in_think and "<think>" in buf:
                        pre, _, rest = buf.partition("<think>")
                        if pre and on_token:
                            on_token(pre)
                        content += pre
                        buf, in_think = rest, True
                        continue
                    if in_think and "</think>" in buf:
                        think, _, rest = buf.partition("</think>")
                        reasoning += think
                        if think and on_thinking:
                            on_thinking(think)
                        buf, in_think = rest, False
                        continue
                    if not in_think and buf:
                        if on_token:
                            on_token(buf)
                        content += buf
                        buf = ""
                    break
            for tc in (delta.get("tool_calls") or []):
                idx = tc.get("index", 0)
                fn = tc.get("function") or {}
                while len(tool_calls) <= idx:
                    tool_calls.append({"id": None, "name": None,
                                       "arguments": ""})
                slot = tool_calls[idx]
                if tc.get("id"):
                    slot["id"] = tc["id"]
                if fn.get("name") and not slot["name"]:
                    slot["name"] = fn["name"]
                slot["arguments"] += fn.get("arguments") or ""
    if buf:
        if in_think:                       # unclosed thinking block
            reasoning += buf
            if on_thinking:
                on_thinking(buf)
        else:
            if on_token:
                on_token(buf)
            content += buf

    # normalize tool call arguments from JSON strings to dicts
    norm = []
    for i, tc in enumerate(tool_calls):
        if not tc.get("name"):
            continue                      # malformed empty-name fragment
        a = tc.get("arguments")
        if isinstance(a, str):
            try:
                a = json.loads(a)
            except Exception:
                a = {}
        norm.append({"id": tc.get("id") or f"call_{i}",
                     "name": tc["name"], "arguments": a or {}})

    # fallback: raw XML tool calls inside content
    if not norm:
        xml = parse_tool_calls(content)
        if xml:
            for i, c in enumerate(xml):
                c["id"] = c.get("id") or f"xml_call_{i}"
            norm = xml
            _, content = split_thinking(content)

    return content, norm, reasoning


if __name__ == "__main__":
    from qwen_template import TOOL_SCHEMAS
    print("[streaming] sending a live test ...")
    text, tools, _ = stream_chat(
        [{"role": "user", "content": "Count from 1 to 5, one per line."}],
        on_token=lambda t: print(t, end="", flush=True))
    print(f"\n[streaming] tools={tools} chars={len(text)}")
