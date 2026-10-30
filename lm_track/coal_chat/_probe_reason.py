import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from streaming import stream_chat

messages = [{"role": "system", "content":
             "The user asked you to create a file. Write the COMPLETE file "
             "content now as plain text (code). Do not describe it, do not "
             "use tool calls, just output the full file body."},
            {"role": "user", "content":
             "make me a html + css + js script where I can play the "
             "classical snake game"}]
text, calls, reason = stream_chat(messages, thinking=True, max_tokens=900)
print("content len:", len(text), "reason len:", len(reason))
print("has fence:", bool(re.search(r"```", reason)))
print("fence langs:", re.findall(r"```(\w*)", reason)[:6])
m = re.search(r"```", reason)
if m:
    print("first fence at char:", m.start())
    print("after fence:", repr(reason[m.start():m.start() + 90]))
# How much prose before the code?
print("--- reason lines 0-6 ---")
for line in reason.splitlines()[:6]:
    print("  ", line[:70])