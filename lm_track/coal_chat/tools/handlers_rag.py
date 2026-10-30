"""Document ingestion + language-pack handlers so Coal can LEARN.

  ingest_docs     -> fetch a URL / read a file / take raw text and add it
                     to the RAG index (chunk -> embed -> store)
  search_docs     -> search what it has learned
  ingest_langpack -> ingest a whole language pack folder
  list_langpacks  -> show what knowledge packs exist

Uses the shared RAG (root = cfg.rag_root) and the local embedder.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from coal_config import cfg

_RAG = None


def _rag():
    global _RAG
    if _RAG is None:
        from rag import RAG
        _RAG = RAG(root=os.path.expanduser(cfg.rag.index_path))
    return _RAG


def _html_to_text(html):
    """Crude HTML -> text (strip scripts/styles/tags)."""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                  flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", html)).strip()


def _fetch(url, max_bytes=400000):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read(max_bytes)
    txt = raw.decode("utf-8", "replace")
    if "<html" in txt.lower() or "<!doctype" in txt.lower():
        txt = _html_to_text(txt)
    return txt


def ingest_docs(args, ctx):
    """Learn from a URL, a file path, a folder, or raw text.

      args:
        url     - fetch this URL and ingest its text
        path    - ingest this file (or folder with recursive=true)
        text    - ingest this raw text
        source  - label to store under (defaults to url/path)
        exts    - comma list for folders (default: docs/code/text)
        recursive - bool for folders
    """
    rag = _rag()
    added = 0
    sources = []
    url = args.get("url")
    path = args.get("path")
    text = args.get("text")

    if url:
        try:
            body = _fetch(url)
        except Exception as e:
            return {"ok": False, "output": f"fetch failed: {e}"}
        added += rag.ingest_text(body, source=args.get("source") or url)
        sources.append(url)
    if path:
        p = os.path.abspath(os.path.expanduser(path))
        if os.path.isdir(p):
            exts = None
            if args.get("exts"):
                exts = {e.strip() if e.strip().startswith(".")
                        else "." + e.strip()
                        for e in str(args["exts"]).split(",")}
            res = rag.ingest_dir(p, exts=exts) if exts else rag.ingest_dir(p)
            added += res.get("chunks", 0)
            sources.append(f"{p} ({res.get('files', 0)} files)")
        elif os.path.isfile(p):
            added += rag.ingest_file(p)
            sources.append(p)
        else:
            return {"ok": False, "output": f"path not found: {p}"}
    if text:
        added += rag.ingest_text(text, source=args.get("source") or "text")
        sources.append("text")

    if not sources:
        return {"ok": False,
                "output": "nothing to ingest: pass url, path, or text"}
    rag.save()
    st = rag.stats()
    return {"ok": True,
            "output": f"Ingested {added} chunks from {', '.join(sources)}. "
                      f"Index now has {st['documents']} chunks from "
                      f"{st['files']} sources."}


def search_docs(args, ctx):
    rag = _rag()
    q = args.get("query", "")
    if not q:
        return {"ok": False, "output": "query required"}
    hits = rag.search(q, k=int(args.get("limit", 5)))
    if not hits:
        return {"ok": True, "output": "no documents match"}
    out = []
    for h in hits:
        src = os.path.basename(h["path"])
        out.append(f"[{src}] {h['text'][:300]}")
    return {"ok": True, "output": "\n\n".join(out)}


# ---- language packs ----
def langpacks_root():
    return os.path.expanduser(
        cfg.get("langpacks", {}).get("root", "~/.coal/langpacks"))


def list_langpacks(args, ctx):
    root = langpacks_root()
    if not os.path.isdir(root):
        return {"ok": True, "output": f"(no language packs yet at {root})"}
    packs = sorted(d for d in os.listdir(root)
                   if os.path.isdir(os.path.join(root, d)))
    lines = []
    for p in packs:
        n = sum(len(fs) for _, _, fs in os.walk(os.path.join(root, p)))
        lines.append(f"- {p}: {n} files")
    return {"ok": True,
            "output": f"language packs at {root}:\n" + "\n".join(lines)}


def ingest_langpack(args, ctx):
    """Ingest one language pack (or all) into the RAG index."""
    name = args.get("name", args.get("pack", ""))
    root = langpacks_root()
    if not os.path.isdir(root):
        return {"ok": False, "output": f"no language packs at {root}"}
    targets = [name] if name else [
        d for d in os.listdir(root)
        if os.path.isdir(os.path.join(root, d))]
    rag = _rag()
    total = 0
    for t in targets:
        p = os.path.join(root, t)
        if os.path.isdir(p):
            res = rag.ingest_dir(p)
            total += res.get("chunks", 0)
    rag.save()
    return {"ok": True,
            "output": f"ingested {total} chunks from language pack(s): "
                      f"{', '.join(targets)}"}


if __name__ == "__main__":
    from types import SimpleNamespace
    ctx = SimpleNamespace(workspace="~/.coal/work")
    print(ingest_docs({"text": "TypeScript interfaces describe the shape "
                       "of an object. Use `interface Foo { x: number }`.",
                       "source": "ts-cheatsheet"}, ctx))
    print(search_docs({"query": "how do I type an object in typescript"},
                      ctx))