import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, ".")
from rox import Rox

r = Rox(session_name="projtest2", auto_start=False)
r._confirm_prompt = lambda q: "you decide"
r.tctx.ask_callback = lambda q: "y"

ans, meta = r.respond("create a project for a web scraper", on_token=lambda t: None)
print("created:", r.project.name)
src = r.project.source

# write main + helper
from tools.exec import ToolExecutor
ex = ToolExecutor(r.tctx, r.perms)
for path, content in [
    (os.path.join(src, "scraper.py"),
     "import requests\nimport parser\n\ndef fetch(url):\n    return requests.get(url).text\n"),
    (os.path.join(src, "parser.py"),
     "def parse(html):\n    return html.upper()\n")]:
    r2 = ex.run("write_file", {"path": path, "content": content})
    print("write:", os.path.basename(path), r2.get("ok"))

# edit scraper.py (journal should show 'edited')
r3 = ex.run("edit_file", {"path": os.path.join(src, "scraper.py"),
                          "old": "return requests.get(url).text",
                          "new": "return requests.get(url, timeout=5).text"})
print("edit:", r3.get("ok"))

from project.journal import Journal
j = Journal(r.project)
print("\n=== journal ===")
print(j.summary())

from project.audit import Auditor
rep = Auditor(r.project).audit()
print("\n=== audit ===")
print(rep["counts"])
for i in rep["issues"][:6]:
    print("  ", i["type"], i["file"], "|", i["detail"][:50])

print("\n=== related(scraper.py) ===")
print(r.project.related("scraper.py"))

print("\n=== project tools via executor ===")
print("audit tool:", ex.run("project_audit", {})["output"].split("\n")[0])
print("journal tool:", ex.run("project_journal", {"limit": 3})["output"].split("\n")[0])
print("map tool first line:", ex.run("project_map", {})["output"].split("\n")[0])

r.close()