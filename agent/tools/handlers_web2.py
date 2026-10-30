"""Category 5 advanced handlers: graphql, ocr (via vision model), package
registry searches, crawl_site (via browser), websocket (honest).
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request


def _fetch(url, data=None, method="GET", headers=None, timeout=30):
    hdr = {"User-Agent": "Coal/1.0"}
    if headers:
        hdr.update(headers)
    body = data.encode("utf-8") if isinstance(data, str) else data
    req = urllib.request.Request(url, data=body, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(200000).decode("utf-8", "replace"), r.status
    except Exception as e:
        return None, str(e)


def graphql_query(args, ctx):
    url = args.get("url", "")
    query = args.get("query", args.get("gql", ""))
    if not url:
        return {"ok": False, "output": "url required"}
    body = json.dumps({"query": query})
    try:
        text, st = _fetch(url, data=body, method="POST",
                          headers={"Content-Type": "application/json"})
        if text is None:
            return {"ok": False, "output": f"request failed: {st}"}
        return {"ok": True, "output": text[:6000]}
    except Exception as e:
        return {"ok": False, "output": f"graphql failed: {e}"}


def websocket_connect(args, ctx):
    return {"ok": False, "output": "websocket not supported in this "
            "synchronous tool. Use web_fetch or http_request instead."}


def search_pypi(args, ctx):
    q = args.get("query", args.get("q", ""))
    try:
        text, st = _fetch(
            "https://pypi.org/pypi/" + urllib.request.quote(q) + "/json")
        if text is None:
            return {"ok": False, "output": f"pypi request failed: {st}"}
        d = json.loads(text)
        info = d.get("info", {})
        return {"ok": True, "output":
                f"pypi: {info.get('name')} {info.get('version')}\n"
                f"{info.get('summary','')[:300]}\n"
                f"home: {info.get('home_page')}"}
    except Exception as e:
        return {"ok": False, "output": f"pypi search failed: {e}"}


def search_npm(args, ctx):
    q = args.get("query", args.get("q", ""))
    try:
        text, st = _fetch("https://registry.npmjs.org/" +
                          urllib.request.quote(q))
        if text is None:
            return {"ok": False, "output": f"npm request failed: {st}"}
        d = json.loads(text)
        return {"ok": True, "output":
                f"npm: {d.get('name')} {d.get('dist-tags',{}).get('latest')}\n"
                f"{d.get('description','')[:300]}"}
    except Exception as e:
        return {"ok": False, "output": f"npm search failed: {e}"}


def search_github(args, ctx):
    q = args.get("query", args.get("q", ""))
    try:
        text, st = _fetch(
            "https://api.github.com/search/repositories?q=" +
            urllib.request.quote(q),
            headers={"Accept": "application/vnd.github+json"})
        if text is None:
            return {"ok": False, "output": f"github request failed: {st} "
                    "(may need gh auth or rate limit)"}
        d = json.loads(text)
        items = d.get("items", [])[:5]
        if not items:
            return {"ok": True, "output": "no repos found"}
        return {"ok": True, "output": "\n".join(
            f"- {i.get('full_name')} ⭐{i.get('stargazers_count')}: "
            f"{i.get('description','')[:120]}" for i in items)}
    except Exception as e:
        return {"ok": False, "output": f"github search failed: {e}"}


def search_stackoverflow(args, ctx):
    q = args.get("query", args.get("q", ""))
    try:
        text, st = _fetch(
            "https://api.stackexchange.com/2.3/search/advanced?"
            "site=stackoverflow&pagesize=5&order=desc&sort=relevance&q=" +
            urllib.request.quote(q))
        if text is None:
            return {"ok": False, "output": f"so request failed: {st}"}
        d = json.loads(text)
        items = d.get("items", [])[:5]
        if not items:
            return {"ok": True, "output": "no results"}
        return {"ok": True, "output": "\n".join(
            f"- {i.get('title')}: {i.get('link')}" for i in items)}
    except Exception as e:
        return {"ok": False, "output": f"stackoverflow failed: {e}"}


def crawl_site(args, ctx):
    from .handlers_browser import browser_navigate
    url = args.get("url", "")
    r = browser_navigate({"url": url}, ctx)
    if not r.get("ok"):
        return r
    return {"ok": True, "output": r["output"][:6000]}


def ocr_image(args, ctx):
    """OCR via the local vision model (Coal mmproj)."""
    path = os.path.abspath(os.path.expanduser(args.get("path", "")))
    if not os.path.exists(path):
        return {"ok": False, "output": f"image not found: {path}"}
    try:
        from vision import ask_about_image
    except Exception:
        return {"ok": False, "output": "vision module unavailable"}
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        text = ask_about_image(b64,
                               "Extract and transcribe all text visible in "
                               "this image. Output the text verbatim.")
        return {"ok": True, "output": text[:6000]}
    except Exception as e:
        return {"ok": False, "output": f"ocr failed: {e}"}


def security_advisory_lookup(args, ctx):
    pkg = args.get("package", args.get("name", ""))
    try:
        text, st = _fetch(
            "https://api.osv.dev/v1/query", data=json.dumps({
                "package": {"name": pkg, "ecosystem": "PyPI"}}),
            method="POST", headers={"Content-Type": "application/json"})
        if text is None:
            return {"ok": False, "output": f"osv request failed: {st}"}
        d = json.loads(text)
        vulns = d.get("vulns", [])[:5]
        if not vulns:
            return {"ok": True, "output": "no known advisories"}
        return {"ok": True, "output": "\n".join(
            f"- {v.get('id')}: {v.get('summary','')[:150]}" for v in vulns)}
    except Exception as e:
        return {"ok": False, "output": f"advisory lookup failed: {e}"}