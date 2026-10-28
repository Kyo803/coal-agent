"""Source discovery — ROX N finds its own material for a topic.

Hubs (no API keys, public, legal): Wikipedia, arXiv, Project Gutenberg,
GitHub. Every fetch passes the guardrails (scheme, robots, rate, content).
Fails soft: offline => empty list, the drive simply moves on.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from . import guardrails

UA = "ROX-N/1.0 (local autonomous learner)"


def _get(url: str, timeout: int = 25) -> str:
    ok, _ = guardrails.allowed_url(url)
    if not ok:
        return ""
    guardrails.polite_wait(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""


def _clean(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>",
                  " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    return re.sub(r"\s+", " ", text).strip()


def wikipedia(topic: str) -> list:
    out = []
    try:
        q = urllib.parse.quote(topic)
        s = _get("https://en.wikipedia.org/w/api.php?action=query&list=search"
                 f"&srsearch={q}&format=json&srlimit=1")
        d = json.loads(s or "{}")
        hits = (((d.get("query") or {}).get("search")) or [])
        if not hits:
            return out
        title = hits[0]["title"]
        t = urllib.parse.quote(title.replace(" ", "_"))
        summary = _get("https://en.wikipedia.org/api/rest_v1/page/summary/" + t)
        sd = json.loads(summary or "{}")
        extract = sd.get("extract") or ""
        url = ((sd.get("content_urls") or {}).get("desktop") or {}).get(
            "page") or f"https://en.wikipedia.org/wiki/{t}"
        full = _get("https://en.wikipedia.org/w/api.php?action=query"
                    f"&prop=extracts&explaintext=1&redirects=1&format=json"
                    f"&titles={q}")
        fd = json.loads(full or "{}")
        pages = (fd.get("query") or {}).get("pages") or {}
        body = ""
        for _, p in pages.items():
            body = p.get("extract") or ""
        text = (extract + "\n\n" + body).strip()
        if text:
            out.append({"title": title, "url": url, "text": text[:20000],
                        "trust": guardrails.trust(url), "kind": "encyclopedia"})
    except Exception:
        pass
    return out


def arxiv(topic: str, max_results: int = 3) -> list:
    out = []
    try:
        q = urllib.parse.quote(f'all:{topic}')
        xml = _get("http://export.arxiv.org/api/query?"
                   f"search_query={q}&start=0&max_results={max_results}")
        for entry in re.findall(r"(?s)<entry>(.*?)</entry>", xml):
            title = re.search(r"(?s)<title>(.*?)</title>", entry)
            summ = re.search(r"(?s)<summary>(.*?)</summary>", entry)
            link = re.search(r'<id>(.*?)</id>', entry)
            if title and summ:
                url = (link.group(1).strip() if link else
                       "https://arxiv.org")
                out.append({"title": re.sub(r"\s+", " ", title.group(1)).strip(),
                            "url": url,
                            "text": re.sub(r"\s+", " ", summ.group(1)).strip(),
                            "trust": guardrails.trust("arxiv.org"),
                            "kind": "paper"})
    except Exception:
        pass
    return out


def gutenberg(topic: str) -> list:
    out = []
    try:
        q = urllib.parse.quote(topic)
        d = json.loads(_get(f"https://gutendex.com/books?search={q}") or "{}")
        for b in (d.get("results") or [])[:3]:
            title = b.get("title") or ""
            authors = ", ".join(a.get("name", "") for a in
                                (b.get("authors") or []))
            txt = ""
            for fmt, url in (b.get("formats") or {}).items():
                if fmt.startswith("text/plain"):
                    txt = _get(url, timeout=30)
                    break
            body = (f"{title} by {authors}\n\n" + (txt[:40000] if txt else
                    (b.get("summaries") or [""])[0]))
            out.append({"title": f"{title} — {authors}".strip(" —"),
                        "url": f"https://www.gutenberg.org/ebooks/{b.get('id')}",
                        "text": body.strip(),
                        "trust": guardrails.trust("gutenberg.org"),
                        "kind": "book"})
    except Exception:
        pass
    return out


def github(topic: str) -> list:
    out = []
    try:
        q = urllib.parse.quote(topic)
        d = json.loads(_get("https://api.github.com/search/repositories?"
                            f"q={q}&sort=stars&per_page=3") or "{}")
        for it in (d.get("items") or [])[:3]:
            out.append({"title": it.get("full_name", ""),
                        "url": it.get("html_url", ""),
                        "text": (it.get("description") or "") +
                                f"\nstars={it.get('stargazers_count')} "
                                f"lang={it.get('language')}",
                        "trust": guardrails.trust("github.com"),
                        "kind": "repo"})
    except Exception:
        pass
    return out


def discover(topic: str, kinds=("encyclopedia", "paper", "repo")) -> list:
    """Return a deduped, trust-ranked list of sources for a topic."""
    buckets = {"encyclopedia": wikipedia, "paper": arxiv,
               "book": gutenberg, "repo": github}
    found, seen = [], set()
    for kind in kinds:
        fn = buckets.get(kind)
        if not fn:
            continue
        for s in fn(topic):
            ok, _ = guardrails.check(s["url"], s.get("text"))
            if not ok:
                continue
            key = s["url"]
            if key in seen:
                continue
            seen.add(key)
            found.append(s)
    found.sort(key=lambda s: -s.get("trust", 0.5))
    return found
