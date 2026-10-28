"""Sandbox lifecycle: start / stop / status of the isolated distro."""
from __future__ import annotations

import time

from . import base


def is_running(timeout: int = 30) -> bool:
    return base.run("echo ready", timeout=timeout)["rc"] == 0


def start(timeout: int = 120) -> bool:
    return base.run("echo ready", timeout=timeout)["rc"] == 0


def ensure() -> bool:
    return start()


def stop() -> dict:
    return base.terminate(base.DISTRO)


def restart(wait: int = 3) -> bool:
    stop()
    time.sleep(wait)
    return start()


def status() -> dict:
    return {
        "distro": base.DISTRO,
        "state": base.distro_state(),
        "running": is_running(),
        "user": base.USER,
        "workdir": base.WORKDIR,
        "distros": base.distro_list(),
    }
