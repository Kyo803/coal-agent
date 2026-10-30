"""Local embeddings for Coal memory.

Priority:
  1. Ollama `nomic-embed-text` (768-d) - real semantic embeddings, local
  2. sentence-transformers MiniLM (384-d)
  3. hashed TF-IDF (no deps, weak)

All backends are local. The backend is reported so the eval suite can
record which was used.
"""
import hashlib
import json
import math
import os
import re
import sys
import urllib.request

# allow running this file directly (adds coal_chat/ to the path)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from coal_config import cfg

STOP = set("a an the is are was were be been to of in on for and or it "
           "this that i you he she we they my your".split())

# Ollama is launched CPU-only + keep-alive 0 so it NEVER competes with
# the Coal model for GPU VRAM (a loaded Ollama model was starving the
# 35B's decode buffers -> empty replies).
OLLAMA_EXE = r"C:\Users\WERU1\AppData\Local\Programs\Ollama\ollama.exe"


def _ollama_env():
    env = dict(os.environ)
    env["OLLAMA_VULKAN"] = "0"
    env["OLLAMA_GPU"] = "0"
    env["OLLAMA_KEEP_ALIVE"] = "0"
    env["OLLAMA_CONTEXT_LENGTH"] = "2048"
    return env


def ensure_ollama():
    """Start Ollama (CPU-only, keep-alive 0) if not already serving."""
    import subprocess
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=4):
            return True
    except Exception:
        pass
    if not os.path.exists(OLLAMA_EXE):
        return False
    try:
        lf = open(os.path.join(os.path.expanduser("~/.coal"),
                               "ollama.log"), "a", encoding="utf-8")
        subprocess.Popen([OLLAMA_EXE, "serve"], stdout=lf,
                         stderr=subprocess.STDOUT,
                         cwd=os.path.dirname(OLLAMA_EXE),
                         env=_ollama_env(),
                         creationflags=0x00000008 | 0x00000200)
        # wait for it to come up
        for _ in range(20):
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:11434/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=3):
                    return True
            except Exception:
                import time
                time.sleep(0.5)
    except Exception:
        pass
    return False


class Embedder:
    def __init__(self, dim=None, backend=None, model=None, url=None):
        self.backend = backend or cfg.memory.embed_backend
        self.model = model or cfg.memory.embed_model
        self.url = (url or cfg.memory.ollama_url).rstrip("/")
        self.dim = dim or 768
        self._st = None
        if self.backend == "ollama" and not self._ollama_ok():
            self.backend = "st"
        if self.backend == "st":
            try:
                from sentence_transformers import SentenceTransformer
                self._st = SentenceTransformer(
                    "sentence-transformers/all-MiniLM-L6-v2",
                    cache_folder="models/embeddings")
                self.dim = self._st.get_sentence_embedding_dimension()
            except Exception:
                self._st = None
                self.backend = "tfidf"
                self.dim = dim or 384

    def _ollama_ok(self):
        if not ensure_ollama():
            return False
        try:
            req = urllib.request.Request(
                self.url + "/api/embeddings",
                data=json.dumps({"model": self.model,
                                 "prompt": "ping"}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                e = json.loads(r.read().decode()).get("embedding")
                if e:
                    self.dim = len(e)
                    return True
        except Exception:
            return False
        return False

    def embed(self, text):
        if self.backend == "ollama":
            v = self._ollama(text)
            if v:
                return v
            # Ollama hiccuped -> deterministic fallback, correct dim
            return self._tfidf(text)
        if self._st is not None:
            return self._st.encode([text], normalize_embeddings=True)[0] \
                .tolist()
        return self._tfidf(text)

    def embed_many(self, texts):
        if self.backend == "ollama":
            out = []
            for t in texts:
                v = self._ollama(t)
                out.append(v if v else self._tfidf(t))
            return out
        if self._st is not None:
            return self._st.encode(list(texts),
                                   normalize_embeddings=True).tolist()
        return [self._tfidf(t) for t in texts]

    def _ollama(self, text):
        try:
            req = urllib.request.Request(
                self.url + "/api/embeddings",
                data=json.dumps({"model": self.model,
                                 "prompt": text}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                e = json.loads(r.read().decode()).get("embedding")
            if not e:
                return []
            # nomic embeddings are not unit-normalised
            n = math.sqrt(sum(x * x for x in e)) or 1.0
            return [x / n for x in e]
        except Exception:
            return []

    def _tfidf(self, text):
        v = [0.0] * self.dim
        toks = [t for t in re.findall(r"[a-z0-9]+", text.lower())
                if t not in STOP and len(t) > 1]
        for t in toks:
            h = int(hashlib.md5(t.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            v[idx] += sign
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def report(self):
        return f"embedder={self.backend} model={self.model} dim={self.dim}"


if __name__ == "__main__":
    e = Embedder()
    print(e.report())
    a = e.embed("my dog is named Biscuit")
    b = e.embed("what is my dog called?")
    c = e.embed("quantum chromodynamics lattice gauge theory")
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))
    print(f"sim(dog, dog-q) = {dot(a, b):.3f}")
    print(f"sim(dog, physics) = {dot(a, c):.3f}")
    assert dot(a, b) > dot(a, c), "semantic ordering failed"
    print("[embed] semantic ordering OK")
