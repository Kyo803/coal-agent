"""Logging setup for Coal. Quiet by default, verbose on request."""
import logging
import os
import sys

_CONFIGURED = False


def setup(level=None, logfile=None):
    """Configure the root 'coal' logger once. Returns the logger."""
    global _CONFIGURED
    logger = logging.getLogger("coal")
    if _CONFIGURED:
        return logger
    level = level or os.environ.get("COAL_LOG", "WARNING")
    logger.setLevel(getattr(logging, str(level).upper(), logging.WARNING))
    fmt = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    if logfile:
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    logger.propagate = False
    _CONFIGURED = True
    return logger


def get(name="coal"):
    return logging.getLogger(name)
