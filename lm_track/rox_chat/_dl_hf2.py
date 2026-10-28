import json
import os
import time
import urllib.request

from huggingface_hub import hf_hub_download

REPO = "Qwen/Qwen3.6-35B-A3B"
CACHE = r"D:\ROX_N_HF\_hub_cache"
os.makedirs(CACHE, exist_ok=True)

req = urllib.request.Request(
    "https://huggingface.co/api/models/" + REPO + "/tree/main",
    headers={"User-Agent": "rox"})
tree = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
files = [x["path"] for x in tree if x.get("type") == "file"]
files = [f for f in files if not f.endswith((".bin", ".onnx", ".msgpack"))]
print(f"[dl] {len(files)} files to fetch", flush=True)

t0 = time.time()
for i, f in enumerate(files, 1):
    try:
        p = hf_hub_download(REPO, f, cache_dir=CACHE, resume_download=True)
    except Exception as e:
        print(f"[dl] FAIL {f}: {e}", flush=True)
        continue
    sz = os.path.getsize(p) / 1e9 if os.path.exists(p) else 0
    print(f"[dl] [{i}/{len(files)}] {f} {sz:.2f} GB "
          f"({time.time()-t0:.0f}s)", flush=True)
print(f"[dl] DONE in {time.time()-t0:.0f}s", flush=True)