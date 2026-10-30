"""Coal model server lifecycle manager.

Handles starting / stopping / health-checking the local llama.cpp server
for Qwen3.6-35B-A3B, with a RAM guard and GPU-layer auto-tune.

  from server_manager import ServerManager
  sm = ServerManager()
  sm.ensure()            # start if not running
  sm.status()            # dict
  sm.stop()

GPU auto-tune: tries to offload layers to the GPU; if the Vulkan/CUDA
allocation fails it falls back to CPU automatically.
"""
import ctypes
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

from coal_config import cfg

CREATE_NO_WINDOW = 0x08000000
DETACHED = 0x00000008 | 0x00000200  # NEW_PROCESS_GROUP | NEW_PROCESS


def free_ram_gb():
    try:
        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        ms = MS()
        ms.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return ms.ullAvailPhys / 1e9
    except Exception:
        return -1.0


class ServerManager:
    def __init__(self, config=cfg):
        self.cfg = config
        self.base = config.base_url
        self.log_path = os.path.join(config.observability.log_dir,
                                     "llama_server.log")
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    # ---- health ----
    def health(self, timeout=4):
        try:
            with urllib.request.urlopen(self.base + "/models",
                                        timeout=timeout) as r:
                return bool(json.loads(r.read().decode()).get("data")
                            or json.loads(r.read().decode()).get("models"))
        except Exception:
            return False

    def model_id(self):
        try:
            with urllib.request.urlopen(self.base + "/models",
                                        timeout=6) as r:
                d = json.loads(r.read().decode())
                items = d.get("data") or d.get("models") or []
                if items:
                    return items[0].get("id") or items[0].get("model")
        except Exception:
            pass
        return None

    # ---- process ----
    @staticmethod
    def _procs():
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq llama-server.exe",
                 "/FO", "CSV", "/NH"],
                creationflags=CREATE_NO_WINDOW, text=True, timeout=10)
            return [l for l in out.splitlines() if "llama-server" in l]
        except Exception:
            return []

    def is_running(self):
        return len(self._procs()) > 0

    # ---- start / stop ----
    def start(self, gpu_layers=None, wait=True, timeout=420):
        import os as _os
        if _os.environ.get("COAL_NO_35B"):
            return False
        if self.health():
            return True
        # Also guard on an existing llama-server process: while a server is
        # still loading the model it is not yet HTTP-healthy, so a second
        # caller could otherwise start a duplicate (two servers = 2x VRAM
        # = OOM). Wait briefly for the existing process to become healthy.
        if self.is_running():
            for _ in range(60):
                if self.health():
                    return True
                time.sleep(1)
            # stuck: a stale process that never comes up -> restart below
            self.stop()
            time.sleep(2)
        exe = self.cfg.server_path()
        model = self.cfg.model_path()
        if not (exe and os.path.exists(exe)):
            raise FileNotFoundError(f"server exe missing: {exe}")
        if not (model and os.path.exists(model)):
            raise FileNotFoundError(f"model missing: {model}")

        # llama.cpp memory-maps the GGUF, so only the working set (KV cache
        # + active layers) must be resident, not the whole file. Guard on a
        # minimum free-RAM floor rather than the full model size.
        min_free = float(self.cfg.model.get("min_free_ram_gb", 3.0))
        free = free_ram_gb()
        if 0 < free < min_free:
            raise MemoryError(
                f"need >= {min_free:.1f}GB free RAM (mmap working set), "
                f"only {free:.1f}GB available. Close apps or use a "
                f"smaller model.")

        if gpu_layers is None:
            gpu_layers = self.cfg.model.gpu_layers
        gpu_layers = int(gpu_layers)

        args = [exe, "-m", model,
                "--host", self.cfg.model.host,
                "--port", str(self.cfg.model.port),
                "-c", str(self.cfg.model.context),
                "-ngl", str(gpu_layers),
                "-t", str(self.cfg.model.threads),
                "--no-webui"]
        if self.cfg.model.get("vision") and self.cfg.mmproj_path() \
                and os.path.exists(self.cfg.mmproj_path()):
            args += ["--mmproj", self.cfg.mmproj_path(),
                     "--image-min-tokens", "1024"]

        args += self._speed_args()
        extra = self.cfg.model.get("extra_args") or []
        if isinstance(extra, (list, tuple)):
            args += [str(a) for a in extra]

        logf = open(self.log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(args, stdout=logf, stderr=subprocess.STDOUT,
                                cwd=os.path.dirname(exe),
                                creationflags=DETACHED)
        if not wait:
            return True
        # wait for health; if GPU offload failed (OOM), step layers down and
        # retry; if it hits 0, run CPU-only.
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.health():
                return True
            if gpu_layers > 0 and self._gpu_oom():
                step = max(1, gpu_layers // 2)
                gpu_layers = max(0, gpu_layers - step)
                self.stop()
                time.sleep(2)
                return self.start(gpu_layers=gpu_layers, wait=wait,
                                  timeout=timeout)
            time.sleep(3)
        return False

    def _speed_args(self):
        """Phase 0 speed/context flags: KV-cache quantization, flash
        attention, prompt cache reuse, optional MoE CPU offload, and
        speculative decoding via a small draft model (same tokenizer)."""
        m = self.cfg.model
        extra = []
        if m.get("flash_attn"):
            extra += ["-fa", "on"]
        if m.get("kv_type_k"):
            extra += ["-ctk", str(m.kv_type_k)]
        if m.get("kv_type_v"):
            extra += ["-ctv", str(m.kv_type_v)]
        if int(m.get("n_cpu_moe") or 0) > 0:
            extra += ["-ncmoe", str(int(m.n_cpu_moe))]
        if int(m.get("cache_reuse") or 0) > 0:
            extra += ["--cache-reuse", str(int(m.cache_reuse))]
        if m.get("spec_type"):
            extra += ["--spec-type", str(m.spec_type)]
        draft = self.cfg.draft_path()
        if draft and os.path.exists(draft):
            extra += ["-md", draft,
                      "--spec-draft-n-max",
                      str(int(m.get("spec_draft_n_max", 16))),
                      "--spec-draft-n-min",
                      str(int(m.get("spec_draft_n_min", 0))),
                      "-ngld", str(int(m.get("draft_gpu_layers", 0)))]
            if m.get("draft_kv_type_k"):
                extra += ["-ctkd", str(m.draft_kv_type_k)]
            if m.get("draft_kv_type_v"):
                extra += ["-ctvd", str(m.draft_kv_type_v)]
        return extra

    def _gpu_oom(self):
        try:
            with open(self.log_path, encoding="utf-8",
                      errors="ignore") as f:
                txt = f.read()
            return any(n in txt for n in (
                "failed to allocate", "OutOfDeviceMemory",
                "failed to fit params to free device memory"))
        except Exception:
            return False

    def stop(self):
        try:
            subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"],
                           creationflags=CREATE_NO_WINDOW, timeout=15)
            time.sleep(2)
            return True
        except Exception:
            return False

    def restart(self, **kw):
        self.stop()
        time.sleep(2)
        return self.start(**kw)

    def ensure(self):
        import os as _os
        if _os.environ.get("COAL_NO_35B"):
            return False
        if self.health():
            return True
        return self.start()

    def status(self):
        return {
            "running": self.is_running(),
            "healthy": self.health(),
            "model": self.model_id(),
            "base_url": self.base,
            "free_ram_gb": round(free_ram_gb(), 1),
            "log": self.log_path,
        }


if __name__ == "__main__":
    sm = ServerManager()
    print(json.dumps(sm.status(), indent=1))
    print("[server_manager] ensuring server ...")
    ok = sm.ensure()
    print("[server_manager] up:", ok)
    if ok:
        print(json.dumps(sm.status(), indent=1))
