"""Configuration: dataclasses + TOML load/save + environment overrides.

Priority: explicit arg > environment variable > config file > default.
Config file default location: ~/.coal/config.toml
"""
import os
import tomllib
from dataclasses import dataclass, field, asdict
from pathlib import Path

from coal.errors import ConfigError

DEFAULT_HOME = os.environ.get("COAL_HOME", os.path.expanduser("~/.coal"))


@dataclass
class BackendConfig:
    # "auto" | "qwen" | "v2" | "hf"
    name: str = "auto"
    # LM Studio / OpenAI-compatible local server
    lmstudio_url: str = "http://localhost:1234/v1"
    lmstudio_model: str = "qwen3.6-35b-a3b"
    lmstudio_timeout: int = 120
    # our from-scratch checkpoint (optional)
    local_model: str = ""
    # small HF fallback
    hf_model: str = "HuggingFaceTB/SmolLM2-135M-Instruct"


@dataclass
class MemoryConfig:
    enabled: bool = True
    root: str = DEFAULT_HOME
    embed_dim: int = 384
    embed_backend: str = "auto"          # auto | minilm | tfidf
    context_budget_tokens: int = 1200
    working_turns: int = 8
    consolidate_every: int = 8


@dataclass
class SafetyConfig:
    enabled: bool = True
    backstop: bool = True                # thin hard classifier
    block_on_crisis: bool = True


@dataclass
class GenerationConfig:
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 768


@dataclass
class Config:
    backend: BackendConfig = field(default_factory=BackendConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    log_level: str = "WARNING"

    # ---- env overrides ----
    def apply_env(self):
        b = self.backend
        b.name = os.environ.get("COAL_BACKEND", b.name)
        b.lmstudio_url = os.environ.get("COAL_LMSTUDIO_URL", b.lmstudio_url)
        b.lmstudio_model = os.environ.get(
            "COAL_LMSTUDIO_MODEL", b.lmstudio_model)
        b.local_model = os.environ.get("COAL_LOCAL_MODEL", b.local_model)
        b.hf_model = os.environ.get("COAL_HF_MODEL", b.hf_model)
        self.memory.root = os.environ.get("COAL_HOME", self.memory.root)
        self.log_level = os.environ.get("COAL_LOG", self.log_level)
        return self


def config_path():
    return os.environ.get("COAL_CONFIG",
                          os.path.join(DEFAULT_HOME, "config.toml"))


def load_config(path=None):
    """Load config from TOML (if present), then apply env overrides."""
    cfg = Config()
    path = path or config_path()
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            raise ConfigError(f"cannot parse {path}: {e}")
        for section, dc in (("backend", cfg.backend),
                            ("memory", cfg.memory),
                            ("safety", cfg.safety),
                            ("generation", cfg.generation)):
            for k, v in (data.get(section) or {}).items():
                if hasattr(dc, k):
                    setattr(dc, k, v)
        if "log_level" in data:
            cfg.log_level = data["log_level"]
    return cfg.apply_env()


def save_config(cfg, path=None):
    """Write config as TOML (minimal writer; flat sections only)."""
    path = path or config_path()
    Path(os.path.dirname(path) or ".").mkdir(parents=True, exist_ok=True)

    def emit(obj):
        lines = []
        for k, v in asdict(obj).items():
            if isinstance(v, bool):
                v = "true" if v else "false"
            elif isinstance(v, str):
                v = '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
            lines.append(f"{k} = {v}")
        return "\n".join(lines)

    parts = ["[backend]\n" + emit(cfg.backend),
             "[memory]\n" + emit(cfg.memory),
             "[safety]\n" + emit(cfg.safety),
             "[generation]\n" + emit(cfg.generation),
             f'log_level = "{cfg.log_level}"']
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(parts) + "\n")
    return path
