"""Exception hierarchy for Coal."""


class CoalError(Exception):
    """Base class for all Coal errors."""


class ConfigError(CoalError):
    """Invalid or missing configuration."""


class BackendError(CoalError):
    """Base class for model-backend errors."""


class BackendUnavailable(BackendError):
    """The requested backend could not be reached or loaded."""


class MemoryError(CoalError):
    """Memory store/index failure (named to avoid shadowing builtins)."""


class SafetyError(CoalError):
    """Safety subsystem failure."""
