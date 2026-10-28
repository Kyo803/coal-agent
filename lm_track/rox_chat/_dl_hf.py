import os
import sys
import time

from huggingface_hub import snapshot_download

REPO = "Qwen/Qwen3.6-35B-A3B"
DST = r"D:\ROX_N_HF\Qwen3.6-35B-A3B"

os.makedirs(DST, exist_ok=True)
print(f"[dl] {REPO} -> {DST}")
t0 = time.time()
path = snapshot_download(
    repo_id=REPO,
    local_dir=DST,
    resume_download=True,
)
print(f"[dl] DONE in {time.time()-t0:.0f}s -> {path}")
# report size
tot = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(DST)
          for f in fs)
print(f"[dl] downloaded bytes: {tot/1e9:.1f} GB")