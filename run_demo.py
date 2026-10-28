"""MVP demo entry point. Stdlib only (no new dependencies).

  python run_demo.py          # live demo: stream + front-end on :8137
  python run_demo.py --smoke  # headless: 600 streamed steps, print numbers

Live: opens http://localhost:8137 — signal trace, surprise trace, unit
grid, FLOPs/latency numbers, INJECT ANOMALY button for the on-demand clip.
"""
import json
import sys
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rox_n.config import MVP_DEFAULT
from rox_n.stream import Streamer

HERE_DIR = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
INDEX = open(__import__("os").path.join(HERE_DIR, "demo", "index.html"),
             encoding="utf-8").read()


def make_handler(streamer: Streamer):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body: bytes, ctype: str):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(INDEX.encode(), "text/html")
            elif self.path == "/api/state":
                self._send(json.dumps(streamer.state()).encode(),
                           "application/json")
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path == "/api/inject":
                streamer.inject()
                self._send(b'{"ok":true}', "application/json")
            else:
                self.send_error(404)

    return H


def smoke(steps=600):
    st = Streamer(MVP_DEFAULT)
    for i in range(steps):
        if i == steps // 2:
            st.inject()  # on-demand clip mid-run, same as stage button
        st.step()
    s = st.summary()
    print(json.dumps(s, indent=2))
    # Stage-readiness gates: savings headline + accuracy close to baseline.
    assert s["flops_saved"] > 0.5, f"savings too low: {s['flops_saved']}"
    assert s["f1_rox"] >= s["f1_den"] - 0.15, (
        f"ROX F1 {s['f1_rox']:.2f} too far below dense {s['f1_den']:.2f}")
    assert s["eme_gate_fraction"] < 1.0, "EME never echoed"
    assert s["plhe_est_fraction"] < 1.0, "PLHE never held"
    print("[smoke] OK: savings headline holds, accuracy close, "
          "all three mechanisms gate on the shared signal.")
    return s


def live(port=8137):
    st = Streamer(MVP_DEFAULT)
    stop = threading.Event()

    def loop():
        period = 1.0 / MVP_DEFAULT.steps_per_sec
        while not stop.is_set():
            t0 = time.perf_counter()
            st.step()
            dt = time.perf_counter() - t0
            time.sleep(max(0.0, period - dt))

    threading.Thread(target=loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", port),
                              make_handler(st))
    print(f"[demo] ROX N live on http://localhost:{port} "
          f"(source={st.meta['source']}, Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        n = 600
        for a in sys.argv[1:]:
            if a.startswith("--steps="):
                n = int(a.split("=")[1])
        smoke(n)
    else:
        port = 8137
        for a in sys.argv[1:]:
            if a.startswith("--port="):
                port = int(a.split("=")[1])
        live(port)
