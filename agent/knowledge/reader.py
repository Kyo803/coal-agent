"""Read any format into text and ingest it (files, URLs, PDFs, docs)."""
from __future__ import annotations

import os


def read_source(target: str) -> str:
    t = (target or "").strip()
    if t.startswith(("http://", "https://")):
        from learning.ingest import fetch_text
        return fetch_text(t)
    if not os.path.exists(t):
        return ""
    ext = os.path.splitext(t)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "")
                             for p in PdfReader(t).pages)
        except Exception:
            return ""
    if ext == ".docx":
        try:
            import docx
            return "\n".join(p.text for p in docx.Document(t).paragraphs)
        except Exception:
            return ""
    try:
        return open(t, encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""


def ingest(target: str, topic: str | None = None, source: str | None = None):
    text = read_source(target)
    if not text.strip():
        return 0
    from learning.ingest import rag
    n = rag().ingest_text(text[:80000], source=source or target)
    try:
        from learning import notes
        notes.add(topic or os.path.basename(target) or "knowledge", text,
                  source=source or target, kind="reader")
    except Exception:
        pass
    return n
