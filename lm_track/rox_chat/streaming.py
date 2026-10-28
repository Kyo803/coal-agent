"""Streaming client for the local model server (SSE).

Prints tokens as they arrive so a slow 35B reply feels alive instead of
freezing for 40 seconds.

  from streaming import stream_chat
  text = stream_chat(messages, tools=TOOL_SCHEMAS,
                     on_token=lambda t: print(t, end="", flush=True))

Returns the full text plus any tool calls (OpenAI-normalized).
"""
import json
import urllib.request

from rox_config import cfg
from qwen_template import split_thinking, parse_tool_calls


def stream_chat(messages, model=None, base_url=None, tools=None,
                thinking=None, on_token=None, on_thinking=None,
                temperature=None, max_tokens=None, timeout=600,
                tool_choice=None):
    """Stream a chat completion. Returns (content, tool_calls, thinking).

    tool_choice: None/"auto" (let the model choose) or
      {"type": "function", "function": {"name": "write_file"}} to force
      a specific tool call (intent-first path).
    """
    base = (base_url or cfg.base_url).rstrip("/")
    model = model or "local-model"
    thinking = cfg.model.thinking if thinking is None else thinking
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": cfg.model.temperature if temperature is None
        else temperature,
        "max_tokens": cfg.model.max_tokens if max_tokens is None
        else max_tokens,
        "chat_template_kwargs": {"enable_thinking": bool(thinking)},
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"

    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")

    content, tool_calls, reasoning = "", [], ""
    in_think, buf = False, ""
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
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
                fn = tc.get("function") or {}
                name = fn.get("name")
                args = fn.get("arguments") or ""
                # streamed tool calls: name arrives once (first chunk),
                # subsequent chunks carry only arguments.
                if tool_calls and not name and tool_calls[-1].get("name"):
                    tool_calls[-1]["arguments"] += args
                    continue
                if not name:
                    continue  # skip malformed empty-name fragments
                if not tool_calls or tool_calls[-1]["name"] != name:
                    tool_calls.append({"name": name, "arguments": args})
                else:
                    tool_calls[-1]["arguments"] += args
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
    for tc in tool_calls:
        a = tc.get("arguments")
        if isinstance(a, str):
            try:
                a = json.loads(a)
            except Exception:
                a = {}
        norm.append({"name": tc["name"], "arguments": a or {}})

    # fallback: raw XML tool calls inside content
    if not norm:
        xml = parse_tool_calls(content)
        if xml:
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
