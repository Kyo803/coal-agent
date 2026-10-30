"""Safe embedder/RAG access for learning.

Prefers Ollama (nomic, 768-d) but NEVER triggers the sentence-transformers
download fallback (which can hang); if Ollama is unavailable it uses the
dependency-free tfidf embedder at the same 768-d, so the shared RAG index
stays dimension-consistent.
"""
from __future__ import annotations

import os

_emb = None
_rag = None


def embedder():
    global _emb
    if _emb is None:
        from memory.embed import Embedder, ensure_ollama
        if not os.environ.get("COAL_LEARN_NO_LLM") and ensure_ollama():
            _emb = Embedder(backend="ollama")
        else:
            _emb = Embedder(backend="tfidf", dim=768)
    return _emb


def rag():
    global _rag
    if _rag is None:
        from rag import RAG
        _rag = RAG(embedder=embedder())
    return _rag
