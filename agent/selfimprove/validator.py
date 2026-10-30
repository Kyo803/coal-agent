"""Validator: static checks before a change can be applied."""
from __future__ import annotations

import json
import os
import py_compile
import tempfile


def validate_content(path: str, content: str) -> tuple:
    if content is None:
        return False, "no content"
    if path.endswith(".py"):
        fd, tmp = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            py_compile.compile(tmp, doraise=True)
            return True, "python syntax ok"
        except py_compile.PyCompileError as e:
            return False, f"syntax error: {e}"
        except Exception as e:
            return False, str(e)
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
    if path.endswith(".json"):
        try:
            json.loads(content)
            return True, "json ok"
        except Exception as e:
            return False, f"json error: {e}"
    return True, "no static check for this type"


def validate_change(change: dict) -> tuple:
    kind = change.get("kind")
    if kind == "seed":
        topics = change.get("topics") or []
        if not topics or not all(isinstance(t, str) and t.strip()
                                 for t in topics):
            return False, "empty seed topic list"
        return True, f"{len(topics)} seed topics"
    if kind in ("code", "prompt"):
        if change.get("content") is None:
            return False, "content requires review before validation"
        return validate_content(change.get("target", ""), change["content"])
    return True, "nothing to validate"
