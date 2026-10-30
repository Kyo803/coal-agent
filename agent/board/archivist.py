"""The archivist: a small local model (coaln-3b) that reads each exchange
(including Coal's own reasoning) and writes structured, provenance-rich
cards onto the board.

Runs in the IDLE window only: it parks the 35B (frees RAM), runs the
archivist on the pending queue, then reloads the 35B. This is the same
time-slice pattern as resources.py (image generation).

Why a small model: memory-building is bookkeeping — a 3B model is cheap,
fast enough, and good at structured JSON. It keeps the 35B free.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coal_config import cfg
from memory.embed import ensure_ollama
from board.queue import Queue

ARCH_SYSTEM = (
    "You are Coal's archivist. You read one exchange between the user and "
    "Coal (including Coal's internal reasoning) and extract durable, "
    "structured knowledge for Coal's long-term board. Output ONLY JSON, "
    "no prose, shaped exactly like:\n"
    '{"title": "short conversation title",'
    '"summary": "1-2 sentence summary of what happened",'
    '"topics": ["topic", ...],'
    '"entities": [{"name": "exact name", "kind": '
    '"person|project|tool|file|place|org|concept|event|decision|task"}],'
    '"relations": [{"src": "entity name", "dst": "entity name",'
    ' "relation": "short_verb_phrase"}],'
    '"facts": ["durable fact about the user/project"],'
    '"decisions": ["decision that was made"],'
    '"tasks": ["open task / next step"],'
    '"questions": ["open question"],'
    '"confidence": 0.0}\n'
    "Rules: only include things worth remembering across sessions; do NOT "
    "invent anything not present; keep names verbatim; if nothing is "
    "worth storing return empty arrays. confidence is 0..1. ALWAYS include "
    "the primary subject of the conversation (the project, person, or thing "
    "being discussed) as an entity, and add a relation whenever two "
    "entities are clearly connected."
)


class Archivist:
    def __init__(self, board, embedder, index, server_manager=None,
                 config=cfg):
        self.board = board
        self.embedder = embedder
        self.index = index
        self.sm = server_manager
        b = config.get("board", {}) or {}
        self.model = b.get("model", "coaln-3b")
        self.url = (b.get("ollama_url") or config.memory.ollama_url).rstrip("/")
        self.park = bool(b.get("park_35b", True))
        self.root = config.memory_root
        self.num_ctx = int(b.get("num_ctx", 4096))

    # ---- model call (Ollama) ----
    def _chat(self, messages, keep_alive="10m", timeout=240):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "keep_alive": keep_alive,
            "options": {"temperature": 0.2, "num_ctx": self.num_ctx},
        }
        req = urllib.request.Request(
            self.url + "/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return ((d.get("message") or {}).get("content") or "").strip()

    def _unload(self):
        try:
            payload = {"model": self.model, "keep_alive": 0}
            req = urllib.request.Request(
                self.url + "/api/generate",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30):
                pass
        except Exception:
            pass

    def available(self):
        return ensure_ollama()

    # ---- extraction ----
    def extract(self, job):
        """Return the structured dict for one exchange, or None."""
        user = (job.get("user_text") or "")[:2000]
        thinking = (job.get("thinking") or "")[:2000]
        output = (job.get("output") or "")[:2500]
        tools = job.get("tools") or []
        convo = (f"USER:\n{user}\n\n"
                 f"Coal REASONING (internal):\n{thinking}\n\n"
                 f"Coal REPLY:\n{output}\n\n"
                 f"TOOLS USED: {', '.join(tools) if tools else 'none'}")
        text = self._chat([
            {"role": "system", "content": ARCH_SYSTEM},
            {"role": "user", "content": convo}])
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    # ---- batch run (idle window) ----
    def run(self, progress_cb=None, should_abort=None):
        """Process the pending queue. Parks the 35B, runs the archivist,
        reloads the 35B. Returns a small report dict.

        should_abort(): if it returns True between jobs (e.g. the user
        started typing), we stop early and reload the 35B.
        """
        q = Queue(self.root)
        jobs = q.pending()
        if not jobs:
            return {"processed": 0, "built": 0, "skipped": 0}

        if not self.available():
            return {"processed": 0, "built": 0,
                    "error": "ollama unavailable"}

        parked = False
        if self.park and self.sm is not None:
            if progress_cb:
                progress_cb("parking 35B")
            try:
                self.sm.stop()
                parked = True
            except Exception:
                parked = False
            self._wait_ram()

        done, built, failed = [], 0, 0
        try:
            for j in jobs:
                if should_abort and should_abort():
                    break
                try:
                    data = self.extract(j)
                    if data:
                        from board.builder import build_card
                        build_card(self.board, self.embedder, self.index,
                                   j, data)
                        built += 1
                    done.append(j["id"])
                except Exception:
                    failed += 1
                if progress_cb:
                    progress_cb(f"archived {built}")
        finally:
            self._unload()
            if parked:
                if progress_cb:
                    progress_cb("reloading 35B")
                try:
                    self.sm.ensure()
                except Exception:
                    pass

        q.remove(done)
        return {"processed": len(done), "built": built, "failed": failed}

    def _wait_ram(self, target_gb=5.0, timeout=120):
        from server_manager import free_ram_gb
        t0 = time.time()
        while time.time() - t0 < timeout:
            if free_ram_gb() >= target_gb:
                return True
            time.sleep(2)
        return False


if __name__ == "__main__":
    # live smoke (needs Ollama + coaln-3b); parks nothing if no sm given
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    from board.store import BoardStore
    from memory import Embedder, VectorIndex
    d = os.path.join(os.path.expanduser("~"), ".coal")
    st = BoardStore(os.path.join(d, "board.db"))
    em = Embedder()
    ix = VectorIndex(os.path.join(d, "vectors"), dim=em.dim)
    a = Archivist(st, em, ix, server_manager=None)
    out = a.extract({"user_text": "I'm building an industrial robot arm with "
                                  "NEMA 23 motors",
                     "thinking": "the user is describing a hardware project",
                     "output": "Nice — NEMA 23 steppers are a solid choice."})
    print("[archivist] extracted:", json.dumps(out)[:400])
    st.close()
