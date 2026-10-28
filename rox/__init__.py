"""ROX N — fully local, memory-persistent AI assistant.

Public API:
    from rox import Rox, Config
    r = Rox()                 # auto-selects the best local backend
    reply = r.chat("hello")   # remembers across sessions

Low-level:
    from rox.memory import Memory
    from rox.backends import get_backend
"""
from rox.config import Config, load_config, save_config
from rox.session import Rox
from rox.errors import (
    RoxError, BackendError, BackendUnavailable, MemoryError, SafetyError,
    ConfigError,
)

__version__ = "1.0.0"

__all__ = [
    "Rox", "Config", "load_config", "save_config",
    "RoxError", "BackendError", "BackendUnavailable", "MemoryError",
    "SafetyError", "ConfigError",
    "__version__",
]
