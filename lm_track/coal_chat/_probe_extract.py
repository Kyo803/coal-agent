import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from streaming import stream_chat
from coal import _extract_file_body

messages = [{"role": "system", "content":
             "The user asked you to create a file. Write the COMPLETE file "
             "content now as plain text (code). Do not describe it, do not "
             "use tool calls, just output the full file body."},
            {"role": "user", "content":
             "make me a html + css + js script where I can play the "
             "classical snake game"}]
text, calls, reason = stream_chat(messages, thinking=True, max_tokens=900)
body = _extract_file_body(text) or _extract_file_body(reason)
print("BODY len:", len(body))
print("BODY first 120:", repr(body[:120]))
print("starts with html?", body.lstrip().lower().startswith(("<html", "<!doctype")))