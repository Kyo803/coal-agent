import sys, io, json, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")

def chat(payload):
    req = urllib.request.Request(
        "http://127.0.0.1:1234/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())

tools = [{"type": "function", "function": {
    "name": "write_file",
    "description": "Write a file.",
    "parameters": {"type": "object", "properties": {
        "path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"]}}}]

forced = {"type": "function", "function": {"name": "write_file"}}

# Test 1: forced tool_choice
d = chat({"model": "x", "stream": False, "max_tokens": 300,
          "temperature": 0.2, "tools": tools,
          "tool_choice": forced,
          "messages": [{"role": "user", "content":
                        "make a file called guard.py that blocks SQL injection"}]})
m = d["choices"][0]["message"]
print("FORCED -> finish:", d["choices"][0].get("finish_reason"))
print("  content:", repr((m.get("content") or "")[:100]))
print("  tool_calls:", json.dumps(m.get("tool_calls"))[:200])

# Test 2: auto tool_choice
d = chat({"model": "x", "stream": False, "max_tokens": 300,
          "temperature": 0.2, "tools": tools,
          "tool_choice": "auto",
          "messages": [{"role": "user", "content":
                        "make a file called guard.py that blocks SQL injection"}]})
m = d["choices"][0]["message"]
print("AUTO -> finish:", d["choices"][0].get("finish_reason"))
print("  content:", repr((m.get("content") or "")[:100]))
print("  tool_calls:", json.dumps(m.get("tool_calls"))[:200])