import os
import sys
import threading
import http.server
import functools

name = sys.argv[1] if len(sys.argv) > 1 else "modern-portfolio"
dist = os.path.join(r"C:\Users\WERU1\OneDrive\Desktop\Coal Projects", name, "dist")
handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                            directory=dist)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8932), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

from playwright.sync_api import sync_playwright

errors = []
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page()
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto("http://127.0.0.1:8932", wait_until="networkidle", timeout=60000)
    info = {
        "title": pg.title(),
        "h1": pg.eval_on_selector_all("h1, h2", "els => els.length"),
        "nav": pg.locator("nav").count(),
        "has_hero": pg.locator("section#hero, .hero, section:has(h1)").count() > 0,
        "has_about": pg.locator("section#about, section:has-text('About')").count() > 0,
        "has_projects": pg.locator("section#projects, section:has-text('Projects')").count() > 0,
        "has_contact": pg.locator("section#contact, section:has-text('Contact')").count() > 0,
        "body_text_len": len(pg.inner_text("body")),
        "console_errors": errors[:5],
    }
    b.close()
srv.shutdown()
for k, v in info.items():
    print(f"{k}: {v}")