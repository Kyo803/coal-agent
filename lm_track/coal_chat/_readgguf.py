import sys

from gguf import GGUFReader

p = sys.argv[1]
r = GGUFReader(p)


def scalar(name):
    f = r.fields.get(name)
    if f is None:
        return "(absent)"
    v = f.contents()
    if hasattr(v, "dtype"):
        import numpy as np
        if v.dtype == np.uint8:
            return bytes(v).decode("utf-8", "replace")
    if isinstance(v, list) and len(v) == 1:
        return v[0]
    return v


arch = scalar("general.architecture")
print("path:", p)
print("architecture:", arch)
print("pre:", scalar("tokenizer.ggml.pre"))
print("model:", scalar("tokenizer.ggml.model"))
for k in ("bos_token_id", "eos_token_id", "padding_token_id",
          "tokenizer.ggml.bos_token_id", "tokenizer.ggml.eos_token_id"):
    print(k, "=", scalar(k))
tok = r.fields.get("tokenizer.ggml.tokens")
print("vocab_size:", len(tok.data) if tok is not None else None)
mrg = r.fields.get("tokenizer.ggml.merges")
print("merges:", len(mrg.data) if mrg is not None else None)