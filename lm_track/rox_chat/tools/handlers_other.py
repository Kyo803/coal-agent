"""Category 4, 5, 7 handlers: git, web/information, database/data.
"""
from __future__ import annotations

import json
import os
import subprocess


def _run(cmd, ctx, timeout=120):
    shell = os.name == "nt"
    try:
        r = subprocess.run(cmd, shell=shell, capture_output=True, text=True,
                           timeout=timeout, cwd=ctx.workspace or None,
                           encoding="utf-8", errors="replace")
        return {"ok": True, "output": f"exit={r.returncode}\n"
                + (r.stdout or "")[-4000:] + (r.stderr or "")[-1500:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"timeout after {timeout}s"}
    except Exception as e:
        return {"ok": False, "output": f"exec failed: {e}"}


# ================= 4. git =================
def git_status(args, ctx):
    return _run("git status --short", ctx)


def git_diff(args, ctx):
    return _run("git diff --stat", ctx)


def git_log(args, ctx):
    n = int(args.get("limit", 20))
    return _run(f"git log --oneline -{n}", ctx)


def git_blame(args, ctx):
    return _run(f"git blame {args.get('file', '')}", ctx)


def git_show(args, ctx):
    return _run(f"git show {args.get('ref', 'HEAD')}", ctx)


def git_add(args, ctx):
    return _run(f"git add {args.get('path', '.')}", ctx)


def git_commit(args, ctx):
    return _run(f"git commit -m {json.dumps(args.get('message',''))}", ctx)


def git_branch(args, ctx):
    return _run("git branch", ctx)


def git_checkout(args, ctx):
    return _run(f"git checkout {args.get('branch', args.get('ref', ''))}", ctx)


def git_merge(args, ctx):
    return _run(f"git merge {args.get('branch', '')}", ctx)


def git_pull(args, ctx):
    return _run("git pull", ctx)


def git_push(args, ctx):
    return _run("git push", ctx)


def git_fetch(args, ctx):
    return _run("git fetch --all", ctx)


def git_clone(args, ctx):
    url = args.get("url", "")
    dst = args.get("path", "")
    return _run(f"git clone {url} {dst}".strip(), ctx, timeout=600)


def git_stash(args, ctx):
    return _run("git stash", ctx)


def git_tag(args, ctx):
    return _run("git tag", ctx)


def git_reset(args, ctx):
    return _run(f"git reset {args.get('ref', 'HEAD')}", ctx)


# ================= 5. web / information =================
def _ssl_ctx():
    """Use certifi's CA bundle; the Windows store often breaks urlopen."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def web_fetch(args, ctx):
    import urllib.request
    url = args.get("url", "")
    try:
        req = urllib.request.Request(url, headers={"User-Agent":
                                                   "ROX-N/1.0"})
        with urllib.request.urlopen(req, timeout=30,
                                    context=_ssl_ctx()) as r:
            data = r.read(int(args.get("max_bytes", 60000)))
            text = data.decode("utf-8", "replace")
        return {"ok": True, "output": text[:6000]}
    except Exception as e:
        return {"ok": False, "output": f"fetch failed: {e}"}


def http_request(args, ctx):
    import urllib.request
    import urllib.parse
    url = args.get("url", "")
    method = args.get("method", "GET")
    body = args.get("body", "")
    try:
        data = body.encode() if body else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type":
                                              "application/json"})
        with urllib.request.urlopen(req, timeout=30,
                                    context=_ssl_ctx()) as r:
            return {"ok": True, "output": f"{r.status}\n"
                    + r.read(60000).decode("utf-8", "replace")[:5000]}
    except Exception as e:
        return {"ok": False, "output": f"request failed: {e}"}


def read_pdf(args, ctx):
    import io
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"ok": False,
                "output": "pypdf not installed; run: pip install pypdf"}
    path = os.path.abspath(os.path.expanduser(args.get("path", "")))
    try:
        r = PdfReader(path)
        txt = "\n".join((p.extract_text() or "") for p in r.pages[:20])
        return {"ok": True, "output": txt[:6000] or "(no extractable text)"}
    except Exception as e:
        return {"ok": False, "output": f"pdf read failed: {e}"}


def read_docx(args, ctx):
    try:
        import docx
    except ImportError:
        return {"ok": False, "output": "python-docx not installed"}
    path = os.path.abspath(os.path.expanduser(args.get("path", "")))
    try:
        d = docx.Document(path)
        txt = "\n".join(p.text for p in d.paragraphs[:200])
        return {"ok": True, "output": txt[:6000]}
    except Exception as e:
        return {"ok": False, "output": f"docx read failed: {e}"}


def csv_transform(args, ctx):
    import csv
    import io
    path = os.path.abspath(os.path.expanduser(args.get("path", "")))
    try:
        with open(path, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        n = int(args.get("limit", 30))
        out = io.StringIO()
        w = csv.writer(out)
        for r in rows[:n]:
            w.writerow(r)
        return {"ok": True, "output": f"{len(rows)} rows\n" + out.getvalue()[:6000]}
    except Exception as e:
        return {"ok": False, "output": f"csv failed: {e}"}


def _bing_search(query, limit=5):
    """Pure-urllib Bing search fallback (no deps). Returns list of
    (title, url)."""
    import base64 as _b64
    import re as _re
    import urllib.parse
    import urllib.request
    url = ("https://www.bing.com/search?q=" + urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read(300000).decode("utf-8", "replace")
    results = []
    for m in _re.finditer(
            r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a></h2>',
            html, _re.S):
        href, title_html = m.group(1), m.group(2)
        title = _re.sub(r"<[^>]+>", "", title_html).strip()
        if not title:
            continue
        # decode the real URL from Bing's u=a1<base64> redirect param
        real = href
        um = _re.search(r"u=a1([A-Za-z0-9+/=]+)", href)
        if um:
            try:
                real = _b64.urlsafe_b64decode(um.group(1) + "==").decode(
                    "utf-8", "replace")
            except Exception:
                pass
        results.append((title, real))
        if len(results) >= limit:
            break
    return results


def web_search(args, ctx):
    """Search the web. Prefers the local ddgs package if installed,
    else a pure-urllib Bing fallback (no install)."""
    q = args.get("query", "")
    if not q:
        return {"ok": False, "output": "query required"}
    limit = int(args.get("limit", 5))
    try:
        from ddgs import DDGS
        with DDGS() as d:
            res = list(d.text(q, max_results=limit))
        out = "\n".join(f"- {r['title']}: {r['href']}"
                        for r in res[:limit]) or "no results"
        return {"ok": True, "output": out}
    except ImportError:
        pass  # fall through to the built-in search
    except Exception:
        pass  # ddgs failed -> use the fallback too
    try:
        results = _bing_search(q, limit)
        if not results:
            return {"ok": True, "output": "no results"}
        return {"ok": True,
                "output": "\n".join(f"- {t}: {h}" for t, h in results)}
    except Exception as e:
        return {"ok": False, "output": f"search failed: {e}"}


# ================= 7. database / data =================
def sql_query(args, ctx):
    import sqlite3
    path = args.get("database", args.get("db", ""))
    sql = args.get("query", "")
    if not os.path.isabs(path):
        path = os.path.join(ctx.workspace or ".", path)
    if not os.path.exists(path):
        return {"ok": False, "output": f"db not found: {path}"}
    try:
        conn = sqlite3.connect(path)
        cur = conn.execute(sql)
        rows = cur.fetchmany(int(args.get("limit", 50)))
        cols = [d[0] for d in cur.description] if cur.description else []
        out = " | ".join(cols) + "\n" if cols else ""
        out += "\n".join(" | ".join(str(c) for c in r) for r in rows)
        conn.close()
        return {"ok": True, "output": out[:6000]}
    except Exception as e:
        return {"ok": False, "output": f"sql failed: {e}"}


def list_tables(args, ctx):
    return sql_query({"database": args.get("database", ""),
                      "query": "SELECT name FROM sqlite_master "
                               "WHERE type='table'"}, ctx)


def describe_table(args, ctx):
    return sql_query({"database": args.get("database", ""),
                      "query": f"PRAGMA table_info({args.get('table','')})"},
                     ctx)


def data_analysis(args, ctx):
    import statistics
    nums = args.get("values", [])
    try:
        nums = [float(x) for x in nums]
    except Exception:
        return {"ok": False, "output": "values must be numeric"}
    if not nums:
        return {"ok": False, "output": "empty list"}
    return {"ok": True, "output": f"n={len(nums)} mean={statistics.mean(nums):.3f} "
            f"median={statistics.median(nums):.3f} stdev="
            f"{statistics.stdev(nums) if len(nums)>1 else 0:.3f} "
            f"min={min(nums)} max={max(nums)}"}