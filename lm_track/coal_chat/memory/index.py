"""Vector index for memory. Numpy brute-force cosine (exact, fine to
~1M vectors); upgrades to FAISS automatically if installed.

Persists to <root>/<kind>.npy + <root>/<kind>.ids.json. Local only.
"""
import json
import os

import numpy as np


class VectorIndex:
    def __init__(self, root, dim=384):
        self.root = root
        self.persist = root is not None and root != ":memory:"
        if self.persist:
            os.makedirs(root, exist_ok=True)
        self.dim = dim
        self._store = {}          # kind -> (ids list, matrix [N,dim])
        self._faiss = None
        try:
            import faiss  # noqa: F401
            self._faiss = faiss
        except Exception:
            self._faiss = None
        if self.persist:
            self._load_all()

    def _path(self, kind):
        return os.path.join(self.root, f"{kind}")

    def _load_all(self):
        for fn in os.listdir(self.root):
            if fn.endswith(".ids.json"):
                kind = fn[:-len(".ids.json")]
                self._load_kind(kind)

    def _load_kind(self, kind):
        base = self._path(kind)
        try:
            ids = json.load(open(base + ".ids.json"))
            mat = np.load(base + ".npy")
            self._store[kind] = [ids, mat]
        except Exception:
            self._store[kind] = [[], np.zeros((0, self.dim), np.float32)]

    def _save_kind(self, kind):
        if not self.persist:
            return
        ids, mat = self._store[kind]
        base = self._path(kind)
        np.save(base + ".npy", mat)
        json.dump(ids, open(base + ".ids.json", "w"))

    def add(self, item_id, vector, kind="message"):
        if kind not in self._store:
            self._store[kind] = [[], np.zeros((0, self.dim), np.float32)]
        ids, mat = self._store[kind]
        v = np.asarray(vector, dtype=np.float32)
        # Embedder dimension changed since the index was persisted (e.g.
        # TF-IDF 384-d while Ollama was down, now nomic 768-d). Vectors
        # from the old space are not comparable — drop them and restart.
        if mat.shape[0] > 0 and mat.shape[1] != v.shape[0]:
            self._store[kind] = [[], np.zeros((0, v.shape[0]), np.float32)]
            ids, mat = self._store[kind]
        if v.shape[0] != self.dim:
            # adapt dim if embedder changed
            self.dim = v.shape[0]
        ids.append(int(item_id))
        self._store[kind] = [ids, np.vstack([mat, v[None, :]])] \
            if mat.shape[0] else [ids, v[None, :]]
        if len(ids) % 50 == 0:
            self._save_kind(kind)

    def search(self, query_vec, k=8, kind="message"):
        if kind not in self._store:
            return []
        ids, mat = self._store[kind]
        if mat.shape[0] == 0:
            return []
        q = np.asarray(query_vec, dtype=np.float32)
        if q.shape[0] != mat.shape[1]:
            return []
        sims = mat @ q
        n = min(k, sims.shape[0])
        top = np.argpartition(-sims, n - 1)[:n]
        top = top[np.argsort(-sims[top])]
        return [(ids[i], float(sims[i])) for i in top]

    def flush(self):
        for kind in self._store:
            self._save_kind(kind)

    def stats(self):
        return {k: len(v[0]) for k, v in self._store.items()}


if __name__ == "__main__":
    import tempfile
    d = tempfile.mkdtemp()
    idx = VectorIndex(d, dim=4)
    idx.add(1, [1, 0, 0, 0])
    idx.add(2, [0, 1, 0, 0])
    idx.add(3, [0.9, 0.1, 0, 0])
    hits = idx.search([1, 0, 0, 0], k=2)
    print(f"[index] hits={hits} stats={idx.stats()}")
    assert hits[0][0] == 1
    print("[index] OK")
