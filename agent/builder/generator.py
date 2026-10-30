"""Generator: produce code units with the local model (35B server).

Graceful: if the model server is down, `available()` is False and callers
fall back to a template/skip. Generation is always *contract-aware* so new
units keep the declared interfaces.
"""
from __future__ import annotations

import json
import urllib.request

from coal_config import cfg


def available(timeout: int = 4) -> bool:
    try:
        with urllib.request.urlopen(cfg.base_url + "/models",
                                    timeout=timeout):
            return True
    except Exception:
        return False


def _chat(messages, max_tokens=1500, temperature=0.3, timeout=600,
          thinking=False) -> str:
    body = {"model": "local", "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature,
            "stream": False, "enable_thinking": thinking,
            "chat_template_kwargs": {"enable_thinking": thinking}}
    try:
        req = urllib.request.Request(
            cfg.base_url + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return (d["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return ""


_SYS = (
    "You are Coal's builder. Write ONLY the file contents for the "
    "requested file and language in one code block. No explanations, no "
    "prose, no markdown outside the block. Keep it small, correct, and "
    "idiomatic."
)


def generate_unit(path: str, spec: str, contract, objectives: dict,
                  context: str = "", stack: str = "node",
                  retries: int = 3) -> str:
    ex = contract.get(path) if contract else {}
    user = (f"FILE: {path}\nSTACK: {stack}\n"
            f"MUST EXPORT: {ex.get('exports')}\n"
            f"IMPORTS: {ex.get('imports')}\n\nSPEC:\n{spec}\n\n"
            f"CONTEXT:\n{context[:2000]}")
    messages = [{"role": "system", "content": _SYS},
                {"role": "user", "content": user}]
    temps = (0.2, 0.5, 0.1, 0.35)
    for i in range(max(1, retries)):
        text = _chat(messages, max_tokens=1400, temperature=temps[i % 4],
                     timeout=420, thinking=False)
        code = _extract_code(text)
        if code:
            return code
    # last resort: return whatever the model produced (even unparsed)
    return _extract_code(_chat(messages, max_tokens=1400,
                               temperature=0.4, timeout=420,
                               thinking=False))


_FENCE_LANGS = {"ts", "tsx", "js", "jsx", "python", "py", "verilog", "v",
                "c", "cpp", "c++", "h", "hpp", "cxx", "text", "makefile"}


def _extract_code(text: str) -> str:
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            body = parts[1]
            if "\n" in body and body.split("\n", 1)[0].strip().lower() in \
                    _FENCE_LANGS:
                body = body.split("\n", 1)[1]
            return body.strip("\n")
    return text.strip()
