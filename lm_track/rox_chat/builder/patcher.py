"""Patcher: minimal, surgical edits per error class.

Auto-fixable classes get deterministic fixes; anything else returns None,
which signals the loop to escalate to regeneration/restructure instead of
thrashing.
"""
from __future__ import annotations

import posixpath

from sandbox import sb

AUTO = {"syntax", "type", "interface"}


def patch_file(cwd: str, rel: str, fix_text: str) -> bool:
    if not rel or fix_text is None:
        return False
    dest = posixpath.join(cwd, rel) if not rel.startswith("/") else rel
    return sb.write(dest, fix_text)


def suggest(cwd: str, diagnosis: dict, fix_text: str | None = None) -> str | None:
    """Return the fixed file text, or None if a safe patch isn't possible."""
    cls = (diagnosis or {}).get("class")
    rel = (diagnosis or {}).get("file")
    if fix_text is not None and rel:
        return fix_text
    if cls not in AUTO or not rel:
        return None
    return None  # no generic heuristic; caller regenerates the unit


def apply(cwd: str, diagnosis: dict, fix_text: str | None = None) -> bool:
    rel = (diagnosis or {}).get("file")
    text = suggest(cwd, diagnosis, fix_text)
    if text is None or not rel:
        return False
    return patch_file(cwd, rel, text)
