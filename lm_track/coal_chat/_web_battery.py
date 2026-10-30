"""Build several websites through one agent session, then verify output."""
import json
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.expanduser(r"~\.coal\work\web_test")
BUILDER = os.path.expanduser(r"~\OneDrive\Desktop\Coal Projects")
os.makedirs(ROOT, exist_ok=True)

SITES = [
    ("store",
     "Create an Amazon-like storefront called 'Nile' directly in the "
     "directory {d}\\store using write_file (do NOT use build_project). "
     "HTML/CSS/JS only. It must include: a search bar that filters products "
     "live, category chips, product cards with rating stars and price, an "
     "add-to-cart that opens a slide-out cart, quantity update, subtotal, "
     "and a mock checkout. Create index.html, styles.css and app.js, and "
     "finish by summarising what you built."),
    ("portfolio",
     "Create a personal portfolio website for a hardware engineer directly "
     "in {d}\\portfolio using write_file (do NOT use build_project). "
     "HTML/CSS/JS only. Sections: hero, about, selected projects (chip "
     "designs with real metrics), skills, contact. Include a dark/light "
     "theme toggle and smooth scrolling. Create index.html, styles.css and "
     "app.js, then summarise what you built."),
    ("three3d",
     "Create an interactive 3D website about chip design directly in "
     "{d}\\three3d using write_file (do NOT use build_project). Use Three.js "
     "from a CDN with an animated rotating chip die, OrbitControls, a "
     "starfield, scroll-driven camera movement, and overlay sections "
     "(hero, architecture, verification, contact). Create index.html, "
     "styles.css and app.js, then summarise what you built."),
]

CHECKS = {
    "store": ["search", "cart", "checkout"],
    "portfolio": ["projects", "skills", "contact"],
    "three3d": ["three", "canvas", "camera"],
}


class Repl:
    def __init__(self):
        self.tools, self.answer, self.done = [], "", None
        self.lock = threading.Lock()
        self.p = subprocess.Popen(
            [sys.executable, "-u", "coal.py", "--json-repl"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.p.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get("t")
            if t == "tool":
                with self.lock:
                    self.tools.append(o.get("name"))
            elif t == "confirm":
                try:
                    self.p.stdin.write(json.dumps({"confirm": True}) + "\n")
                    self.p.stdin.flush()
                except Exception:
                    pass
            elif t == "answer":
                with self.lock:
                    self.answer = o.get("text") or ""
            elif t == "done":
                with self.lock:
                    self.done = o

    def run(self, prompt, timeout=480):
        with self.lock:
            self.tools, self.answer, self.done = [], "", None
        time.sleep(2.0)
        try:
            self.p.stdin.write(json.dumps({"prompt": prompt}) + "\n")
            self.p.stdin.flush()
        except Exception:
            return
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                if self.done:
                    return
            time.sleep(0.3)

    def kill(self):
        try:
            self.p.kill()
        except Exception:
            pass


def find_dir(name):
    for base in (os.path.join(ROOT, name), os.path.join(BUILDER, name)):
        if os.path.isdir(base):
            return base
    return None


def verify(name):
    d = find_dir(name)
    if not d:
        return {"ok": False, "why": "no directory", "dir": None}
    files = []
    for base, _dirs, fs in os.walk(d):
        for f in fs:
            p = os.path.join(base, f)
            files.append((os.path.relpath(p, d), os.path.getsize(p)))
    idx = os.path.join(d, "index.html")
    if not os.path.exists(idx):
        return {"ok": False, "why": "no index.html", "files": files,
                "dir": d}
    html = open(idx, encoding="utf-8", errors="ignore").read()
    low = html.lower()
    alltext = low
    for f, _sz in files:
        if f.endswith((".js", ".css")):
            try:
                alltext += open(os.path.join(d, f), encoding="utf-8",
                                errors="ignore").read().lower()
            except Exception:
                pass
    missing = [k for k in CHECKS[name] if k not in alltext]
    ok = (len(html) > 1200 and "<html" in low and "</html" in low
          and not missing)
    return {"ok": ok, "why": ("ok" if ok else f"missing {missing}"),
            "bytes": len(html), "files": files, "dir": d}


results = []
repl = Repl()
for name, tpl in SITES:
    prompt = tpl.format(d=ROOT)
    t0 = time.time()
    repl.run(prompt)
    with repl.lock:
        tools = list(repl.tools)
        ans = repl.answer
        done = repl.done
    v = verify(name)
    rec = {"site": name, "tools": tools, "answer": ans, "verify": v,
           "ms": (done or {}).get("ms"),
           "wall_s": round(time.time() - t0, 1)}
    results.append(rec)
    print(f"== {name}: tools={tools} verify={v.get('ok')} "
          f"({v.get('why')}) {rec['wall_s']}s", flush=True)
    print(f"   dir: {v.get('dir')}", flush=True)
    for f, sz in (v.get("files") or []):
        print(f"     {f:28s} {sz:>7d} B", flush=True)
    print((ans or "")[:400].replace("\n", " "), flush=True)
    print(flush=True)
repl.kill()

with open(os.path.join(ROOT, "web_results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=1)
print("written", os.path.join(ROOT, "web_results.json"))
