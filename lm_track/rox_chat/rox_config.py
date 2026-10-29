"""ROX N configuration loader.

Reads config.json from the install directory (Program Files / per-user
Programs). Every module imports `cfg` from here so paths and settings
live in exactly one place.

  from rox_config import cfg
  cfg.model.gguf
  cfg.memory.root          # expanded
  cfg.port

Env overrides: ROX_CONFIG (path to config.json), ROX_PORT, ROX_MODEL.
"""
import json
import os


DEFAULT_INSTALL = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Programs", "ROX N")

SEARCH_PATHS = [
    os.environ.get("ROX_CONFIG"),
    os.path.join(DEFAULT_INSTALL, "config.json"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"),
]


class _Section(dict):
    """Dict with attribute access: cfg.model.gguf."""

    def __getattr__(self, k):
        try:
            v = self[k]
        except KeyError:
            raise AttributeError(k)
        return _Section(v) if isinstance(v, dict) else v

    def __setattr__(self, k, v):
        self[k] = v


class Config(_Section):
    def __init__(self, path=None):
        self._path = path or self._find()
        data = {}
        if self._path and os.path.exists(self._path):
            data = json.load(open(self._path, encoding="utf-8"))
        super().__init__(data)
        self._apply_defaults()
        self._apply_env()

    def _find(self):
        for p in SEARCH_PATHS:
            if p and os.path.exists(p):
                return p
        return None

    def _apply_defaults(self):
        self.setdefault("install_dir", DEFAULT_INSTALL)
        self.setdefault("model", {})
        self.model.setdefault("host", "127.0.0.1")
        self.model.setdefault("port", 1234)
        self.model.setdefault("context", 8192)
        self.model.setdefault("gpu_layers", 0)
        self.model.setdefault("threads", max(4, (os.cpu_count() or 4) - 2))
        self.model.setdefault("thinking", False)
        self.model.setdefault("vision", True)
        self.model.setdefault("max_tokens", 1024)
        self.model.setdefault("temperature", 0.6)
        self.model.setdefault("hf_source", "")
        self.model.setdefault("hf_repos", [])
        # --- speed & context (Phase 0) ---
        self.model.setdefault("flash_attn", False)
        self.model.setdefault("kv_type_k", "")
        self.model.setdefault("kv_type_v", "")
        self.model.setdefault("cache_reuse", 0)
        self.model.setdefault("n_cpu_moe", 0)
        # speculative decoding
        self.model.setdefault("draft_gguf", "")
        self.model.setdefault("spec_type", "")
        self.model.setdefault("spec_draft_n_max", 16)
        self.model.setdefault("spec_draft_n_min", 0)
        self.model.setdefault("draft_gpu_layers", 0)
        self.model.setdefault("draft_kv_type_k", "")
        self.model.setdefault("draft_kv_type_v", "")
        # MoE / task-specialization
        self.model.setdefault("profile", "chat")
        self.model.setdefault("extra_args", [])
        self.setdefault("moe", {"profile_default": "chat",
                                "expert_paging": True})
        self.setdefault("memory", {"min_headroom_gb": 1.5,
                                   "park_ollama_when_tight": True})
        self.setdefault("router", {"auto_route": True})
        self.setdefault("memory", {})
        self.memory.setdefault("root", "~/.rox")
        self.memory.setdefault("embed_backend", "ollama")
        self.memory.setdefault("embed_model", "nomic-embed-text")
        self.memory.setdefault("ollama_url", "http://localhost:11434")
        self.memory.setdefault("consolidate_every", 8)
        self.memory.setdefault("recall_k", 8)
        self.setdefault("personality", {"name": "Rox",
                                        "adapt_to_user": True,
                                        "base_traits": {}})
        self.setdefault("rag", {"watch_dirs": [],
                                "index_path": "~/.rox/rag",
                                "chunk_chars": 800})
        self.setdefault("board", {})
        self.board.setdefault("model", "roxn-3b")
        self.board.setdefault("ollama_url",
                              self.memory.get("ollama_url",
                                              "http://localhost:11434"))
        self.board.setdefault("idle_seconds", 60)
        self.board.setdefault("auto_archive", False)
        self.board.setdefault("park_35b", True)
        self.board.setdefault("provenance", "full")
        self.board.setdefault("num_ctx", 4096)
        self.board.setdefault("budget_tokens", 700)
        self.setdefault("chip", {})
        self.chip.setdefault("model", "chip-design-ai-v4")
        self.chip.setdefault("ollama_url",
                             self.memory.get("ollama_url",
                                             "http://localhost:11434"))
        self.setdefault("learning", {})
        self.learning.setdefault("model", "roxn-3b")
        self.learning.setdefault("ollama_url",
                                 self.memory.get("ollama_url",
                                                 "http://localhost:11434"))
        self.learning.setdefault("num_ctx", 4096)
        self.learning.setdefault("allow_network", True)
        self.learning.setdefault("source_kinds",
                                 ["encyclopedia", "paper", "repo"])
        self.learning.setdefault("idle_cycles", 1)
        self.learning.setdefault("night_cycles", 5)
        self.learning.setdefault("max_pages_per_cycle", 4)
        self.learning.setdefault("seed_topics", [
            "mathematics", "physics", "computer science", "algorithms",
            "machine learning", "systems programming", "electronics",
            "digital design", "web engineering", "software architecture"])
        self.setdefault("selfimprove", {})
        self.selfimprove.setdefault("dry_run", True)
        self.selfimprove.setdefault("allow_high_risk", False)
        self.selfimprove.setdefault("use_experiment", True)
        self.selfimprove.setdefault("max_per_cycle", 2)
        self.selfimprove.setdefault("min_interval_s", 300)
        self.setdefault("governance", {})
        self.governance.setdefault("enabled", False)
        self.governance.setdefault("idle_seconds", 120)
        self.governance.setdefault("poll_s", 30)
        self.governance.setdefault("interval_s", 900)
        self.governance.setdefault("night_start", 0)
        self.governance.setdefault("night_end", 7)
        self.governance.setdefault("learning_cycles", 1)
        self.governance.setdefault("night_cycles", 3)
        self.governance.setdefault("run_learning", True)
        self.governance.setdefault("run_observe", True)
        self.governance.setdefault("run_practice", False)
        self.governance.setdefault("run_reflect", True)
        self.governance.setdefault("run_archive", True)
        self.governance.setdefault("run_improve", False)
        self.governance.setdefault("reflect_measure", False)
        self.governance.setdefault("run_retry_missions", True)
        self.governance.setdefault("night_retries", 1)
        self.governance.setdefault("run_mission_queue", True)
        self.setdefault("observability", {})
        self.observability.setdefault(
            "log_dir", os.path.join(self["install_dir"], "logs"))
        self.observability.setdefault("log_level", "info")

    def _apply_env(self):
        if os.environ.get("ROX_PORT"):
            self.model["port"] = int(os.environ["ROX_PORT"])
        if os.environ.get("ROX_MODEL"):
            self.model["gguf"] = os.environ["ROX_MODEL"]

    # ---- helpers ----
    @property
    def base_url(self):
        # explicit override (e.g. a hosted OpenAI-compatible endpoint)
        env = os.environ.get("ROX_BASE_URL")
        if env:
            return env.rstrip("/")
        return f"http://{self.model.host}:{self.model.port}/v1"

    @property
    def memory_root(self):
        return os.path.expanduser(self.memory.root)

    @property
    def rag_root(self):
        return os.path.expanduser(self.rag.index_path)

    def model_path(self):
        return self.model.get("gguf")

    def server_path(self):
        return self.model.get("server_exe")

    def mmproj_path(self):
        return self.model.get("mmproj")

    def draft_path(self):
        return self.model.get("draft_gguf")

    def report(self):
        return {
            "config": self._path,
            "install_dir": self["install_dir"],
            "model": os.path.basename(self.model_path() or "?"),
            "server": os.path.basename(self.server_path() or "?"),
            "port": self.model.port,
            "context": self.model.context,
            "thinking": self.model.thinking,
            "vision": self.model.vision,
            "memory_root": self.memory_root,
            "embed": f"{self.memory.embed_backend}:{self.memory.embed_model}",
        }


cfg = Config()


if __name__ == "__main__":
    print(json.dumps(cfg.report(), indent=1))
    for key, path in (("model", cfg.model_path()),
                      ("server", cfg.server_path()),
                      ("mmproj", cfg.mmproj_path())):
        print(f"  {key:8s} exists={bool(path) and os.path.exists(path)}"
              f"  {path}")
