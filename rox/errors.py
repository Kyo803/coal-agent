"""Exception hierarchy for ROX N."""


class RoxError(Exception):
    """Base class for all ROX N errors."""


class ConfigError(RoxError):
    """Invalid or missing configuration."""


class BackendError(RoxError):
    """Base class for model-backend errors."""


class BackendUnavailable(BackendError):
    """The requested backend could not be reached or loaded."""


class MemoryError(RoxError):
    """Memory store/index failure (named to avoid shadowing builtins)."""


class SafetyError(RoxError):
    """Safety subsystem failure."""
