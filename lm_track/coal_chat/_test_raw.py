import sys, io, json, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")

payload = {
    "model": "x", "stream": False, "max_tokens": 2000, "temperature": 0.3,
    "messages": [
        {"role": "system", "content":
         "The user asked you to create a file. Write the COMPLETE file "
         "content now as plain text (code). Do not describe it, do not use "
         "tool calls, just output the full file body."},
        {"role": "user", "content":
         "make a file called guard.py that blocks SQL injection"}]}
req = urllib.request.Request("http://127.0.0.1:1234/v1/chat/completions",
                             data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"},
                             method="POST")
with urllib.request.urlopen(req, timeout=600) as r:
    d = json.loads(r.read().decode())
m = d["choices"][0]["message"]
print("keys:", list(m.keys()))
print("finish:", d["choices"][0].get("finish_reason"))
print("content:", repr((m.get("content") or "")[:400]))
print("reasoning:", repr((m.get("reasoning_content") or "")[:200]))