"""Package management inside the sandbox (apt / pip / npm)."""
from __future__ import annotations

from . import base


def _pkglist(packages) -> str:
    if isinstance(packages, str):
        packages = [packages]
    return " ".join(base.shq(p) for p in packages if p)


def apt_update(timeout: int = 600) -> dict:
    return base.run("apt-get update -y", root=True, timeout=timeout)


def apt_install(packages, update: bool = False, timeout: int = 1800) -> dict:
    script = ""
    if update:
        script += "apt-get update -y\n"
    script += ("DEBIAN_FRONTEND=noninteractive "
               f"apt-get install -y --no-install-recommends {_pkglist(packages)}")
    return base.run(script, root=True, timeout=timeout)


def apt_remove(packages, timeout: int = 900) -> dict:
    return base.run(f"apt-get remove -y {_pkglist(packages)}", root=True,
                    timeout=timeout)


def pip_install(packages, user: bool = True, timeout: int = 1200) -> dict:
    flag = "--user " if user else ""
    return base.run(f"python3 -m pip install {flag}--upgrade "
                    f"{_pkglist(packages)}", timeout=timeout)


def npm_install(packages, global_: bool = False, cwd: str | None = None,
                timeout: int = 1200) -> dict:
    flag = "-g " if global_ else ""
    return base.run(f"npm install {flag}{_pkglist(packages)}",
                    cwd=cwd, timeout=timeout)


def npm_install_project(cwd: str, timeout: int = 1800) -> dict:
    return base.run("npm install", cwd=cwd, timeout=timeout)


def pnpm_install(cwd: str, timeout: int = 1800) -> dict:
    return base.run("pnpm install", cwd=cwd, timeout=timeout)


def go_get(pkg: str, timeout: int = 900) -> dict:
    return base.run(f"go install {base.shq(pkg)}", timeout=timeout)


def cargo_install(crate: str, timeout: int = 1800) -> dict:
    return base.run(f"cargo install {base.shq(crate)}", timeout=timeout)
