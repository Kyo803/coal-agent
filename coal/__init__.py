"""Coal — fully local, memory-persistent AI assistant.

Public API:
    from coal import Coal, Config
    r = Coal()                 # auto-selects the best local backend
    reply = r.chat("hello")   # remembers across sessions

Low-level:
    from coal.memory import Memory
    from coal.backends import get_backend
"""
from coal.config import Config, load_config, save_config
from coal.session import Coal
from coal.errors import (
    CoalError, BackendError, BackendUnavailable, MemoryError, SafetyError,
    ConfigError,
)

__version__ = "1.0.0"

__all__ = [
    "Coal", "Config", "load_config", "save_config",
    "CoalError", "BackendError", "BackendUnavailable", "MemoryError",
    "SafetyError", "ConfigError",
    "__version__",
]
