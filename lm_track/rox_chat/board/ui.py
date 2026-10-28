"""Detective board UI: a tiny local web server that renders board.db.

Flat, solid-color only (no gradients/images). Serves one page plus a
JSON API the page fetches.

  python board/ui.py            # serve + open browser
  python board/ui.py --port 8790 --no-open

Or from ROX N:  python rox.py --board-ui
"""
from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from board.store import BoardStore

HERE = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(HERE, "ui.html")


def build_data(board, limit=300):
    """Assemble everything the UI needs as one JSON-able dict."""
    nodes = []
    for n in board.top_nodes(limit=limit):
        nbs = board.neighbors(n["id"])[:20]
        nodes.append({
            "id": n["id"], "kind": n["kind"], "name": n["name"],
            "summary": n.get("summary") or "",
            "salience": round(n.get("salience") or 0.0, 2),
            "neighbors": [{"relation": x["relation"], "name": x["name"],
                           "kind": x["kind"], "dir": x["dir"]}
                          for x in nbs],
        })
    dossiers = []
    for d in board.recent_dossiers(limit=limit):
        prov = board.provenance_for("dossier", d["id"], limit=3)
        dossiers.append({
            "id": d["id"], "session_id": d["session_id"],
            "title": d["title"], "summary": d["summary"],
            "topics": d["topics"], "decisions": d["decisions"],
            "tasks": d["tasks"], "questions": d["questions"],
            "entities": d["entities"],
            "provenance": [{"user_text": p["user_text"],
                            "thinking": p["thinking"],
                            "output": p["output"],
                            "confidence": p["confidence"]} for p in prov],
        })
    timeline = [{"ts": e["ts"], "kind": e["kind"], "text": e["text"]}
                for e in board.timeline(limit=100)]
    return {"stats": board.stats(), "nodes": nodes, "dossiers": dossiers,
            "timeline": timeline}


def _handler(board):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/board"):
                data = build_data(board)
                self._send(200, json.dumps(data),
                           "application/json; charset=utf-8")
            elif self.path in ("/", "/index.html"):
                try:
                    html = open(HTML_PATH, encoding="utf-8").read()
                except Exception as e:
                    html = f"<h1>ui.html missing</h1><pre>{e}</pre>"
                self._send(200, html, "text/html; charset=utf-8")
            else:
                self._send(404, "not found", "text/plain")

    return H


def serve(board=None, port=8790, open_browser=True):
    if board is None:
        root = os.path.expanduser("~/.rox")
        board = BoardStore(os.path.join(root, "board.db"))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _handler(board))
    url = f"http://127.0.0.1:{port}/"
    print(f"[board-ui] serving {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[board-ui] stopped")
    finally:
        httpd.server_close()
    return httpd


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    serve(port=a.port, open_browser=not a.no_open)
