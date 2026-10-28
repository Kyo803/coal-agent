import re

tests = [
    "x\n);\n```\n",
    "x\n);\n```",
    "x\n```tsx\n```",
]
for raw in tests:
    body = raw.strip()
    body = re.sub(r"^```[a-zA-Z]*\s*\n?", "", body)
    body = re.sub(r"\n?\s*```\s*$", "", body)
    print(repr(raw), "->", repr(body))