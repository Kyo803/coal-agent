"""ROX N installer: set up the install directory, server and model links.

Idempotent. Finds the model (a local GGUF store or a given path), links
it into the install dir under the ROX N name, copies the server, and
writes config.json.

  python install.py                 # auto-detect
  python install.py --model PATH --server PATH --install DIR
  python install.py --check         # verify only
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INSTALL = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Programs", "ROX N")

# Local GGUF stores searched in order (first hit wins).
MODEL_SEARCH = [
    r"C:\Users\WERU1\AppData\Local\Programs\ROX N\models",
    r"C:\Models",
]
SERVER_SEARCH = [
    r"C:\Users\WERU1\AppData\Local\Programs\ROX N\server",
    r"C:\Users\WERU1\.lmstudio\extensions\backends"
    r"\llama.cpp-win-x86_64-vulkan-avx2-2.46.0",
]

# The install-dir model is stored under the ROX N name (source file is
# linked but the visible name never reveals the origin).
MODEL_NAME = "ROX-N-35B-A3B-Q4_K_M.gguf"
MMPROJ_NAME = "ROX-N-35B-A3B-mmproj-BF16.gguf"


def find_in(dirs, needle):
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if needle.lower() in f.lower():
                return os.path.join(d, f)
    return None


def link(src, dst):
    """Hard link (same volume) or copy."""
    if os.path.exists(dst):
        return "exists"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.link(src, dst)
        return "linked"
    except OSError:
        shutil.copy2(src, dst)
        return "copied"


def install(install_dir, model=None, mmproj=None, server=None):
    print(f"[install] target: {install_dir}")
    os.makedirs(os.path.join(install_dir, "models"), exist_ok=True)
    os.makedirs(os.path.join(install_dir, "server"), exist_ok=True)
    os.makedirs(os.path.join(install_dir, "logs"), exist_ok=True)

    model = model or find_in(MODEL_SEARCH, "Q4_K_M.gguf")
    mmproj = mmproj or find_in(MODEL_SEARCH, "mmproj")
    if not model:
        print("[install] ERROR: model file not found. Pass --model PATH")
        return 1
    m_dst = os.path.join(install_dir, "models", MODEL_NAME)
    print(f"  model : {link(model, m_dst)} -> {MODEL_NAME}")
    mm_dst = None
    if mmproj:
        mm_dst = os.path.join(install_dir, "models", MMPROJ_NAME)
        print(f"  mmproj: {link(mmproj, mm_dst)} -> {MMPROJ_NAME}")

    srv_dir = os.path.join(install_dir, "server")
    server = server or find_in(SERVER_SEARCH, "llama-server.exe")
    if server:
        srcdir = os.path.dirname(server)
        n = 0
        for f in os.listdir(srcdir):
            s = os.path.join(srcdir, f)
            if os.path.isfile(s):
                if link(s, os.path.join(srv_dir, f)) != "exists":
                    n += 1
        print(f"  server: {n} files -> {srv_dir}")
    else:
        print("[install] WARN: llama-server.exe not found")

    cfg = {
        "version": "1.0.0",
        "install_dir": install_dir,
        "model": {
            "name": "ROX-N-35B-A3B",
            "gguf": m_dst,
            "mmproj": mm_dst,
            "server_exe": os.path.join(srv_dir, "llama-server.exe"),
            "host": "127.0.0.1", "port": 1234, "context": 8192,
            "gpu_layers": 0, "threads": max(4, (os.cpu_count() or 4) - 2),
            "thinking": False, "vision": bool(mm_dst), "max_tokens": 1024,
            "temperature": 0.6, "min_free_ram_gb": 3.0,
        },
        "fallback_servers": [
            {"kind": "ollama", "url": "http://localhost:11434/v1",
             "model": "qwen2.5:7b"}],
        "memory": {"root": "~/.rox", "embed_backend": "ollama",
                   "embed_model": "nomic-embed-text",
                   "ollama_url": "http://localhost:11434",
                   "max_facts": 20000, "consolidate_every": 8, "recall_k": 8},
        "personality": {"name": "Rox", "adapt_to_user": True,
                        "base_traits": {"warmth": 0.7, "directness": 0.8,
                                        "humor": 0.4, "formality": 0.3,
                                        "verbosity": 0.4}},
        "rag": {"watch_dirs": [], "index_path": "~/.rox/rag",
                "chunk_chars": 800},
        "observability": {"log_dir": os.path.join(install_dir, "logs"),
                          "log_level": "info", "trace_tools": True},
    }
    cpath = os.path.join(install_dir, "config.json")
    json.dump(cfg, open(cpath, "w", encoding="utf-8"), indent=2)
    print(f"  config: {cpath}")
    return 0


def check(install_dir):
    ok = True
    cfg_path = os.path.join(install_dir, "config.json")
    if not os.path.exists(cfg_path):
        print("  [FAIL] config.json missing")
        return 1
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    for key, p in (("model", cfg["model"]["gguf"]),
                   ("server", cfg["model"]["server_exe"]),
                   ("mmproj", cfg["model"].get("mmproj"))):
        e = bool(p) and os.path.exists(p)
        ok = ok and (e or key == "mmproj")
        print(f"  [{'OK ' if e else 'FAIL'}] {key:7s} {p}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", default=DEFAULT_INSTALL)
    ap.add_argument("--model", default=None)
    ap.add_argument("--mmproj", default=None)
    ap.add_argument("--server", default=None)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        sys.exit(check(args.install))
    rc = install(args.install, args.model, args.mmproj, args.server)
    print("[install] verify:")
    check(args.install)
    print("[install] done." if rc == 0 else "[install] incomplete.")
    sys.exit(rc)


if __name__ == "__main__":
    main()
