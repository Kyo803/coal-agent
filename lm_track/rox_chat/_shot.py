import os
import sys
import subprocess
import time
import threading
import http.server
import functools

ROOT = r"C:\Users\WERU1\OneDrive\Desktop\ROX Projects"
name = sys.argv[1] if len(sys.argv) > 1 else "modern-portfolio"
dist = os.path.join(ROOT, name, "dist")
out = os.path.join(os.path.expanduser("~"), ".rox", f"{name}.png")

if not os.path.isdir(dist):
    print(f"no dist for {name}")
    sys.exit(1)

handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                            directory=dist)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8931), handler)
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto("http://127.0.0.1:8931", wait_until="networkidle", timeout=60000)
    time.sleep(2)
    pg.screenshot(path=out, full_page=True)
    b.close()
srv.shutdown()
print(f"screenshot saved: {out}")