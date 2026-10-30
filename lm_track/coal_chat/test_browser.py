"""Browser-control QA: real interactions on a local page."""
import os
import tempfile

from tools.exec import ToolExecutor

PASS = FAIL = 0


def ok(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  {detail}")


HTML = """<!doctype html>
<html><head><title>QA Page</title></head>
<body>
  <h1 id="h">Hello</h1>
  <input id="name" type="text">
  <button id="btn"
    onclick="document.getElementById('out').textContent=
             'clicked:'+document.getElementById('name').value;
             console.log('btn clicked')">Go</button>
  <div id="out">none</div>
  <script>console.log('page ready');</script>
</body></html>
"""

d = tempfile.mkdtemp(prefix="coalqa_")
page_path = os.path.join(d, "qa.html")
open(page_path, "w", encoding="utf-8").write(HTML)
url = "file:///" + page_path.replace("\\", "/")

ex = ToolExecutor()

print("== navigate ==")
r = ex.run("browser_navigate", {"url": url})
out = r.get("output") or ""
ok("navigate ok", r.get("ok"))
ok("title read", "QA Page" in out, out[:80])

print("\n== evaluate js ==")
r = ex.run("browser_evaluate_js", {"code": "document.title"})
ok("js returns title", "QA Page" in (r.get("output") or ""),
   (r.get("output") or "")[:80])

print("\n== type + click ==")
r = ex.run("browser_type", {"selector": "#name", "text": "coal"})
ok("type ok", r.get("ok"), (r.get("output") or "")[:80])
r = ex.run("browser_click", {"selector": "#btn"})
ok("click ok", r.get("ok"), (r.get("output") or "")[:80])

print("\n== verify state changed ==")
r = ex.run("browser_evaluate_js",
           {"code": "document.getElementById('out').textContent"})
got = r.get("output") or ""
ok("click handler ran", "clicked:coal" in got, got[:120])

print("\n== fill_form ==")
r = ex.run("browser_fill_form",
           {"fields": {"#name": "second"}, "selector": "form"})
ok("fill_form ok", r.get("ok"), (r.get("output") or "")[:80])

print("\n== console logs ==")
r = ex.run("browser_console_logs", {})
got = r.get("output") or ""
ok("console captured page ready", "page ready" in got, got[:120])
ok("console captured click", "btn clicked" in got, got[:120])

print("\n== screenshot ==")
shot = os.path.join(d, "shot.png")
r = ex.run("browser_screenshot", {"path": shot})
ok("screenshot ok", r.get("ok"), (r.get("output") or "")[:80])
ok("screenshot file exists", os.path.exists(shot) and
   os.path.getsize(shot) > 1000)

print("\n== tabs ==")
r = ex.run("browser_tabs", {})
ok("tabs ok", r.get("ok"), (r.get("output") or "")[:100])

print("\n== snapshot ==")
r = ex.run("browser_snapshot", {})
ok("snapshot contains heading", "Hello" in (r.get("output") or ""))

print("\n== wait_for ==")
r = ex.run("browser_wait_for", {"selector": "#out", "timeout": 3000})
ok("wait_for existing element", r.get("ok"), (r.get("output") or "")[:80])

print(f"\n{'='*40}\n{PASS} passed, {FAIL} failed")
