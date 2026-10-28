"""Local embeddings. Prefers sentence-transformers MiniLM; falls back to
a deterministic hashed bag-of-words vector. Never touches the network at
inference (model loaded from local cache only)."""
import hashlib
import logging
import math
import re

log = logging.getLogger("rox.memory.embed")

_STOP = set(
    "a an the is are was were be been to of in on for and or it this that "
    "i you he she we they my your me his her our their".split())


class Embedder:
    def __init__(self, dim=384, backend="auto"):
        self.dim = dim
        self.backend = "tfidf"
        self._model = None
        if backend in ("auto", "minilm"):
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(
                    "sentence-transformers/all-MiniLM-L6-v2",
                    cache_folder="models/embeddings")
                self.dim = self._model.get_sentence_embedding_dimension()
                self.backend = "minilm"
                log.info("embeddings: MiniLM (%d-d)", self.dim)
            except Exception as e:
                if backend == "minilm":
                    raise
                log.info("MiniLM unavailable (%s); using tfidf", e)
                self._model = None
        self._cache = {}

    def embed(self, text):
        key = text[:512]
        if key in self._cache:
            return self._cache[key]
        if self._model is not None:
            v = self._model.encode([text], normalize_embeddings=True)[0]
            v = v.tolist()
        else:
            v = self._tfidf(text)
        if len(self._cache) < 4096:
            self._cache[key] = v
        return v

    def embed_many(self, texts):
        return [self.embed(t) for t in texts]

    def _tfidf(self, text):
        v = [0.0] * self.dim
        for t in re.findall(r"[a-z0-9]+", text.lower()):
            if t in _STOP or len(t) < 2:
                continue
            h = int(hashlib.md5(t.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            v[idx] += sign
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def report(self):
        return {"backend": self.backend, "dim": self.dim}
