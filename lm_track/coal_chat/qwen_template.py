"""Qwen3.6 chat template + native tool-call format.

The model was trained on a specific template (see its model.yaml):
  chat turn   : <|im_start|>role\\n content <|im_end|>
  thinking    : <think> ... </think>  (inside assistant turn)
  tool call   : <tool_call><function=name><parameter=k>v</parameter>
                </function></tool_call>
  tool result : <tool_response> ... </tool_response>
  vision      : <|vision_start|><|image_pad|><|vision_end|>

llama-server normalizes OpenAI-style tool_calls for us, but this module
also parses the model's raw XML (for non-server paths) and renders tool
responses in the exact format the model expects.
"""
import json
import re

IM_START = "<|im_start|>"
IM_END = "<|im_end|>"

# Coal memory tools, in OpenAI schema form (server converts to Qwen XML)
TOOL_SCHEMAS = [
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
            "text": {"type": "string", "description": "the fact"}},
            "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "update_profile",
        "description": "Update the user's profile (style=concise, "
                       "name=WERU, trait:humor=0.7).",
        "parameters": {"type": "object", "properties": {
            "key": {"type": "string"}, "value": {"type": "string"}},
            "required": ["key", "value"]}}},
    {"type": "function", "function": {
        "name": "forget",
        "description": "Delete matching memories (privacy request).",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "search_documents",
        "description": "Search the user's indexed documents/files.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}},
            "required": ["query"]}}},
]

# ---- parsing raw XML tool calls (fallback path) ----
_TC = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.S)
_FN = re.compile(r"<function\s*=\s*([\w]+)\s*>(.*?)</function>", re.S)
_PARAM = re.compile(r"<parameter\s*=\s*([\w]+)\s*>(.*?)</parameter>", re.S)
_THINK = re.compile(r"<think>(.*?)</think>", re.S)


def parse_tool_calls(text):
    """Extract tool calls from raw model output (XML format).
    Returns list of {"name": str, "arguments": dict}."""
    calls = []
    for block in _TC.findall(text or ""):
        m = _FN.search(block)
        if not m:
            continue
        name, body = m.group(1), m.group(2)
        args = {}
        for k, v in _PARAM.findall(body):
            args[k] = v.strip()
        calls.append({"name": name, "arguments": args})
    return calls


def split_thinking(text):
    """Return (thinking, answer) split on <think>...</think>."""
    if not text:
        return "", ""
    m = _THINK.search(text)
    if not m:
        return "", text
    thinking = m.group(1).strip()
    answer = _THINK.sub("", text).strip()
    return thinking, answer


def format_tool_response(result):
    """Render a tool result in the model's expected format."""
    return f"<tool_response>\n{result}\n</tool_response>"


def render_chat(messages, add_generation_prompt=True, thinking=False,
                tools=None):
    """Render a prompt string using the Qwen template (manual path)."""
    out = []
    if tools:
        tool_txt = "# Tools\n\nYou have access to the following functions:"
        for t in tools:
            tool_txt += "\n" + json.dumps(t["function"])
        sys_prefix = tool_txt + "\n</tools>"
        if messages and messages[0].get("role") == "system":
            out.append(f"{IM_START}system\n{sys_prefix}\n\n"
                       f"{messages[0]['content']}{IM_END}\n")
            messages = messages[1:]
        else:
            out.append(f"{IM_START}system\n{sys_prefix}{IM_END}\n")
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "tool":
            content = format_tool_response(content)
            out.append(f"{IM_START}user\n{content}{IM_END}\n")
        else:
            out.append(f"{IM_START}{role}\n{content}{IM_END}\n")
    if add_generation_prompt:
        out.append(f"{IM_START}assistant\n")
        if not thinking:
            out.append("<think>\n\n</think>\n\n")
    return "".join(out)


# base persona (personality.py overrides/adapts this)
BASE_SYSTEM = (
    "You are Coal, a local assistant built in the Coal project. You run "
    "entirely on the user's machine. Use the memory tools whenever the "
    "user refers to past conversations, their projects, preferences, or "
    "personal facts. Be warm, direct and concise. Never invent facts; if "
    "you are unsure, say so."
)


if __name__ == "__main__":
    demo = ("Sure.<tool_call>\n<function=search_memory>\n"
            "<parameter=query>robot arm motors</parameter>\n"
            "</function>\n</tool_call>")
    print("parsed:", parse_tool_calls(demo))
    print("split:", split_thinking("<think>hmm</think>The answer is 4."))
    print("resp:", format_tool_response("NEMA 23"))
    print("--- rendered prompt ---")
    print(render_chat([{"role": "system", "content": BASE_SYSTEM},
                       {"role": "user", "content": "hi"}],
                      tools=TOOL_SCHEMAS)[:400])
