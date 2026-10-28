"""Category 6 handlers: browser + UI via Playwright (persistent, fast).

A single headless Chromium is launched once and reused across calls so
subsequent operations are near-instant. Fully local and private.

All handlers return {"ok", "output"}. Every call auto-navigates to
args.url when given, then performs the action. Timeouts are short
(default 15s navigation) so a slow page fails fast.
"""
from __future__ import annotations

import os
import time

_pw = None
_browser = None
_context = None
_page = None
_lock = False


def _shutdown():
    """Stop Playwright cleanly; otherwise asyncio spews at interpreter exit."""
    global _pw, _browser, _context, _page
    try:
        if _browser is not None:
            _browser.close()
    except Exception:
        pass
    try:
        if _pw is not None:
            _pw.stop()
    except Exception:
        pass
    _browser = _context = _page = _pw = None


try:
    import atexit

    atexit.register(_shutdown)
except Exception:
    pass


def _ensure():
    """Lazily launch the persistent headless Chromium."""
    global _browser, _context, _page, _lock, _pw
    if _browser is not None:
        try:
            return _page
        except Exception:
            _browser = None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    _pw = sync_playwright().start()
    _browser = _pw.chromium.launch(
        headless=True,
        args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
              "--disable-blink-features=AutomationControlled"])
    _context = _browser.new_context(viewport={"width": 1280, "height": 900})
    _page = _context.new_page()
    return _page


def _nav(page, url):
    if not url:
        return
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass


def _snapshot(page):
    """Fast accessibility/DOM snapshot for the model."""
    try:
        title = page.title()
    except Exception:
        title = ""
    try:
        body = page.inner_text("body")[:6000]
    except Exception:
        body = ""
    try:
        url = page.url
    except Exception:
        url = ""
    try:
        visible = page.locator("body > *").count()
    except Exception:
        visible = 0
    return f"URL: {url}\nTITLE: {title}\nVISIBLE_ELEMENTS: {visible}\n\n{body}"


def _cap(text, n=6000):
    text = str(text)
    return text if len(text) <= n else text[:n] + "...[truncated]"


def browser_navigate(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable; "
                "try web_fetch instead"}
    url = args.get("url", "")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        return {"ok": False, "output": f"navigation failed: {e}"}
    return {"ok": True, "output": _snapshot(page)}


def browser_snapshot(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    return {"ok": True, "output": _snapshot(page)}


def browser_screenshot(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    path = args.get("path") or os.path.join(
        getattr(ctx, "workspace", ".") or ".", "screenshot.png")
    try:
        page.screenshot(path=path, full_page=bool(args.get("full_page", False)))
        return {"ok": True, "output": f"saved screenshot -> {path}"}
    except Exception as e:
        return {"ok": False, "output": f"screenshot failed: {e}"}


def browser_click(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    sel = args.get("selector", "")
    try:
        page.click(sel, timeout=8000)
        time.sleep(0.4)
        return {"ok": True, "output": f"clicked {sel}\n{_snapshot(page)}"}
    except Exception as e:
        return {"ok": False, "output": f"click failed: {e}"}


def browser_type(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    sel = args.get("selector", "")
    text = args.get("text", "")
    try:
        page.fill(sel, text)
        return {"ok": True, "output": f"typed into {sel}: {text[:80]}"}
    except Exception:
        try:
            page.click(sel)
            page.keyboard.type(text)
            return {"ok": True, "output": f"typed into {sel}"}
        except Exception as e:
            return {"ok": False, "output": f"type failed: {e}"}


def browser_hover(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    try:
        page.hover(args.get("selector", ""), timeout=8000)
        return {"ok": True, "output": "hovered " + args.get("selector", "")}
    except Exception as e:
        return {"ok": False, "output": f"hover failed: {e}"}


def browser_scroll(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    amount = int(args.get("amount", 500))
    try:
        page.evaluate(f"window.scrollBy(0, {amount})")
        time.sleep(0.3)
        return {"ok": True, "output": f"scrolled {amount}px\n{_snapshot(page)}"}
    except Exception as e:
        return {"ok": False, "output": f"scroll failed: {e}"}


def browser_evaluate_js(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    code = args.get("code", "")
    try:
        out = page.evaluate(code)
        return {"ok": True, "output": _cap(out)}
    except Exception as e:
        return {"ok": False, "output": f"evaluate failed: {e}"}


def browser_wait_for(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    sel = args.get("selector", "")
    ms = int(args.get("timeout", 5000))
    try:
        page.wait_for_selector(sel, timeout=ms)
        return {"ok": True, "output": f"found {sel}\n{_snapshot(page)}"}
    except Exception as e:
        return {"ok": False, "output": f"wait failed: {e}"}


def browser_fill_form(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    fields = args.get("fields") or {}
    try:
        for sel, val in fields.items():
            page.fill(sel, str(val))
        return {"ok": True,
                "output": "filled " + ", ".join(fields.keys())}
    except Exception as e:
        return {"ok": False, "output": f"fill failed: {e}"}


def browser_upload_file(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    sel = args.get("selector", "")
    path = args.get("path", "")
    try:
        page.set_input_files(sel, path)
        return {"ok": True, "output": f"uploaded {path} to {sel}"}
    except Exception as e:
        return {"ok": False, "output": f"upload failed: {e}"}


def browser_handle_dialog(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    page.once("dialog", lambda d: d.accept()
              if args.get("accept", True) else d.dismiss())
    return {"ok": True, "output": "dialog handler set (accept="
            f"{args.get('accept', True)})"}


def browser_console_logs(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    _nav(page, args.get("url", ""))
    logs = []
    try:
        page.on("console", lambda m: logs.append(m.text))
        page.reload()
        time.sleep(0.5)
    except Exception:
        pass
    return {"ok": True, "output": "\n".join(logs[-50:]) or "(no console logs)"}


def browser_network_requests(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    reqs = []
    try:
        page.on("request", lambda r: reqs.append(
            f"{r.method} {r.url[:120]}"))
        _nav(page, args.get("url", ""))
        time.sleep(0.5)
    except Exception:
        pass
    return {"ok": True,
            "output": "\n".join(reqs[-40:]) or "(no requests)"}


def browser_tabs(args, ctx):
    page = _ensure()
    if page is None:
        return {"ok": False, "output": "playwright unavailable"}
    try:
        pages = _context.pages
        return {"ok": True, "output":
                "\n".join(f"{i}: {p.url}" for i, p in enumerate(pages))}
    except Exception as e:
        return {"ok": False, "output": f"tabs failed: {e}"}


def browser_connect(ctx):
    """Return whether the persistent browser is usable."""
    page = _ensure()
    return page is not None


if __name__ == "__main__":
    from types import SimpleNamespace
    ctx = SimpleNamespace(workspace="~/.rox/work")
    r = browser_navigate(
        {"url": "data:text/html,<html><body><h1>Hello ROX</h1>"
                "<p>Playwright test</p></body></html>"}, ctx)
    print("navigate:", r["ok"])
    print(r["output"][:200])
    if r["ok"]:
        r2 = browser_snapshot({}, ctx)
        print("snapshot:", "ROX" in r2["output"], "-", r2["output"][:80])