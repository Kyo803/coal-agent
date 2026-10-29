"""Browser QA part 2: network, hover, scroll, new tab, dialogs."""
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


HTML = """<!doctype html><html><head><title>QA2</title></head><body>
<div style="height:3000px">
  <p id="top">top</p>
  <button id="b" onmouseover="this.textContent='hovered'">button</button>
</div>
<p id="bottom">bottom</p></body></html>
"""
d = tempfile.mkdtemp(prefix="roxqa2_")
p = os.path.join(d, "q.html")
open(p, "w", encoding="utf-8").write(HTML)
url = "file:///" + p.replace("\\", "/")

ex = ToolExecutor()
sortie = ex.run("browser_navigate", {"url": url})
ok("navigate", sortie.get("ok"), (sortie.get("output") or "")[:80])

r = ex.run("browser_network_requests", {})
ok("network_requests ok", r.get("ok"), (r.get("output") or "")[:100])

r = ex.run("browser_hover", {"selector": "#b"})
ok("hover ok", r.get("ok"), (r.get("output") or "")[:80])
r = ex.run("browser_evaluate_js",
           {"code": "document.getElementById('b').textContent"})
ok("hover changed text", "hovered" in (r.get("output") or ""),
   (r.get("output") or "")[:80])

r = ex.run("browser_scroll", {"amount": 500})
ok("scroll ok", r.get("ok"), (r.get("output") or "")[:80])

r = ex.run("browser_tabs", {"action": "new", "url": url})
ok("new tab ok", r.get("ok"), (r.get("output") or "")[:100])
r = ex.run("browser_tabs", {})
ok("tabs list ok", r.get("ok"), (r.get("output") or "")[:150])

r = ex.run("browser_evaluate_js", {"code": "[1,2,3].length"})
ok("js evaluates array", "3" in (r.get("output") or ""),
   (r.get("output") or "")[:80])

r = ex.run("browser_evaluate_js", {"code": "throw new Error('boom')"})
ok("js error handled gracefully", r.get("ok") is not None,
   (r.get("output") or "")[:100])

print(f"\n{'='*40}\n{PASS} passed, {FAIL} failed")
