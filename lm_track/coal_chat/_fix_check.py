import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from coal import Coal

r = Coal(session_name="fixcheck", auto_start=False)
# memory recall (uses embedder -> needs CPU-only Ollama)
q1 = "what motors do I use on my robot arm?"
ans, meta = r.respond(q1, on_token=lambda t: None)
print(f"Q: {q1}\nA [{meta['kind']}]: {ans[:120]}")

# plain chat (the previously-failing case)
q2 = "hi, are you working?"
ans, meta = r.respond(q2, on_token=lambda t: None)
print(f"\nQ: {q2}\nA [{meta['kind']}]: {ans[:120]}")

st = r.status()
print(f"\nserver healthy={st['server']['healthy']} "
      f"free_ram={st['server']['free_ram_gb']}GB tools={st['tools']['registry']}")
r.close()