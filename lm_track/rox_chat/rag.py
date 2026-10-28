"""ROX N RAG: index your documents so the model can answer from them.

Ingests text-like files (txt, md, code, json, csv, html; PDF if pypdf is
installed), chunks them, embeds locally, and stores in a vector index
under <memory_root>/rag/. The model calls `search_documents` (or the
pipeline auto-injects top chunks) to ground answers.

  from rag import RAG
  r = RAG()
  r.ingest_dir(r"C:\\Users\\WERU1\\projects", exts=[".py", ".md"])
  r.search("how does the motor driver work", k=4)
"""
import glob
import json
import os
import re
import time

from rox_config import cfg
from memory.embed import Embedder
from memory.index import VectorIndex

TEXT_EXTS = {".txt", ".md", ".markdown", ".rst", ".py", ".js", ".ts",
             ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".rb",
             ".json", ".yaml", ".yml", ".toml", ".ini", ".csv", ".html",
             ".xml", ".sh", ".bat", ".ps1", ".sql", ".log"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             "dist", "build", ".idea", ".vscode"}


class RAG:
    def __init__(self, root=None, embedder=None):
        self.root = root or cfg.rag_root
        os.makedirs(self.root, exist_ok=True)
        self.embedder = embedder or Embedder()
        self.index = VectorIndex(self.root, dim=self.embedder.dim)
        self.docs_path = os.path.join(self.root, "docs.json")
        self.docs = []
        if os.path.exists(self.docs_path):
            try:
                self.docs = json.load(open(self.docs_path, encoding="utf-8"))
            except Exception:
                self.docs = []

    # ---- chunking ----
    def chunk(self, text):
        width = cfg.rag.chunk_chars
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= width:
            return [text] if len(text) > 40 else []
        chunks, cur = [], ""
        for para in re.split(r"(?<=[.!?])\s+|\n", text):
            if len(cur) + len(para) + 1 <= width:
                cur = (cur + " " + para).strip()
            else:
                if len(cur) > 40:
                    chunks.append(cur)
                cur = para
        if len(cur) > 40:
            chunks.append(cur)
        return chunks

    # ---- ingestion ----
    def _read(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
                return "\n".join((p.extract_text() or "")
                                 for p in PdfReader(path).pages)
            except Exception:
                return ""
        try:
            return open(path, encoding="utf-8", errors="ignore").read()
        except Exception:
            return ""

    def ingest_file(self, path):
        text = self._read(path)
        if not text:
            return 0
        n = 0
        for i, ch in enumerate(self.chunk(text)):
            did = len(self.docs)
            self.docs.append({"path": path, "chunk": i, "text": ch})
            self.index.add(did, self.embedder.embed(ch), kind="docs")
            n += 1
        return n

    def ingest_text(self, text, source="text"):
        """Ingest raw text (e.g. a fetched web page or a snippet) under a
        source label. Returns the number of chunks added."""
        if not text or not text.strip():
            return 0
        n = 0
        for i, ch in enumerate(self.chunk(text)):
            did = len(self.docs)
            self.docs.append({"path": source, "chunk": i, "text": ch})
            self.index.add(did, self.embedder.embed(ch), kind="docs")
            n += 1
        self.save()
        return n

    def ingest_dir(self, directory, exts=None, max_files=2000):
        exts = set(exts or TEXT_EXTS)
        files, added = [], 0
        for dirpath, dirnames, filenames in os.walk(directory):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if os.path.splitext(fn)[1].lower() in exts:
                    files.append(os.path.join(dirpath, fn))
                if len(files) >= max_files:
                    break
            if len(files) >= max_files:
                break
        for fp in files:
            try:
                added += self.ingest_file(fp)
            except Exception:
                continue
        self.save()
        return {"files": len(files), "chunks": added}

    def save(self):
        json.dump(self.docs, open(self.docs_path, "w", encoding="utf-8"))
        self.index.flush()

    # ---- retrieval ----
    def search(self, query, k=None):
        k = k or cfg.memory.recall_k
        hits = self.index.search(self.embedder.embed(query), k=k,
                                 kind="docs")
        out = []
        for did, score in hits:
            if 0 <= did < len(self.docs):
                d = dict(self.docs[did])
                d["score"] = round(score, 4)
                out.append(d)
        return out

    def context(self, query, k=None, max_chars=1600):
        hits = self.search(query, k=k)
        if not hits:
            return ""
        parts, used = [], 0
        for h in hits:
            src = os.path.basename(h["path"])
            piece = f"[{src}] {h['text']}"
            if used + len(piece) > max_chars:
                break
            parts.append(piece)
            used += len(piece)
        return "\n".join(parts)

    def stats(self):
        return {"documents": len(self.docs),
                "files": len({d['path'] for d in self.docs}),
                "vectors": self.index.stats()}


if __name__ == "__main__":
    import tempfile
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "src"), exist_ok=True)
    open(os.path.join(root, "src", "motor.md"), "w").write(
        "The NEMA 23 stepper driver limits current to 2.5A using a "
        "chopper circuit. Configure microstepping to 1/16 for smooth "
        "motion. A flyback diode protects the driver from inductive "
        "voltage spikes when the motor de-energizes.")
    open(os.path.join(root, "src", "canbus.md"), "w").write(
        "CAN bus is a differential bus with 120 ohm termination at each "
        "end. It is robust in industrial environments.")
    r = RAG(root=os.path.join(root, "ragidx"))
    print("ingest:", r.ingest_dir(os.path.join(root, "src")))
    print("stats:", r.stats())
    for q in ["how much current does the stepper driver limit",
              "what terminates a CAN bus"]:
        hits = r.search(q, k=1)
        print(f"  Q: {q}\n    -> {hits[0]['text'][:80] if hits else 'MISS'}")
