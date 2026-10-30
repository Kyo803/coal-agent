"""Ingest: put learned material into RAG (searchable) and notes (auditable).

Reuses the same RAG index the chat uses, so anything learned becomes
immediately answerable via search_docs / the reply pipeline.
"""
from __future__ import annotations

import re
import urllib.request

from . import embed, guardrails, notes

UA = "Coal/1.0 (local autonomous learner)"


def rag():
    return embed.rag()


def fetch_text(url: str, timeout: int = 30) -> str:
    ok, _ = guardrails.allowed_url(url)
    if not ok:
        return ""
    guardrails.polite_wait(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except Exception:
        return ""
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def ingest_source(topic: str, source: dict) -> int:
    text = source.get("text") or ""
    url = source.get("url") or ""
    if not text and url:
        text = fetch_text(url)
    ok, _ = guardrails.check(url or "http://local", text)
    if not ok or not text.strip():
        return 0
    n = rag().ingest_text(text[:60000],
                          source=url or source.get("title") or topic)
    notes.add(topic, text, source=source.get("title"), url=url,
              trust=source.get("trust", 0.5),
              kind=source.get("kind", "web"))
    return n


def ingest_sources(topic: str, sources: list, limit: int = 5) -> dict:
    chunks, used = 0, 0
    for s in sources[:limit]:
        c = ingest_source(topic, s)
        if c:
            used += 1
            chunks += c
    return {"sources": used, "chunks": chunks}


def learn_url(topic: str, url: str) -> dict:
    text = fetch_text(url)
    if not text:
        return {"ok": False, "reason": "fetch failed or blocked"}
    return {"ok": True,
            "chunks": ingest_source(topic, {"url": url, "text": text,
                                            "title": url,
                                            "trust": guardrails.trust(url)})}
