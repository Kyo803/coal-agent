import sys
sys.path.insert(0, ".")
from coal import _extract_file_body

tests = [
    ('write_file(filename="x.py", content="def f(): return 1")',
     "def f(): return 1"),
    ('Here is the code:\n```python\ndef g():\n    return 2\n```',
     "def g():\n    return 2"),
    ('I created the file!\nprint("hello")', 'print("hello")'),
]
ok = 0
for raw, want in tests:
    got = _extract_file_body(raw)
    status = "OK" if want in got else "FAIL"
    if want in got:
        ok += 1
    print(status, "->", repr(got[:70]))
print(f"{ok}/{len(tests)} extraction cases passed")