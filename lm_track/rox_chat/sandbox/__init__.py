"""ROX N sandbox — an isolated Ubuntu (WSL2) that ROX N fully controls.

The sandbox is the security boundary: ROX N may run ANY Linux command,
install any package, clone any repo, and build any project inside it,
while the Windows host is sealed off (automount + interop disabled).

    from sandbox import sb
    sb.shell("ls -la")
    sb.write("/home/rox/work/x.py", "print('hi')")
    sb.pkg_install("python3-numpy")      # apt
    sb.pip_install("requests")
    sb.info()

Modules:
    base     low-level `wsl bash -s` bridge + distro control
    exec     run/check/which/version
    fs       read/write/edit/list/move/remove
    session  start/stop/status
    health   OS + tool versions
    pkg      apt/pip/npm installs
    toolchain per-stack install (web/python/cpp/hdl/rust/go)
    governor host/sandbox resource budget
"""
from __future__ import annotations

from . import base, session, health, pkg, toolchain, governor
from . import exec as _exec
from . import fs as _fs

shell = _exec.shell
check = _exec.check
which = _exec.which
version = _exec.version
read = _fs.read
read_text = _fs.read_text
write = _fs.write
append = _fs.append
edit = _fs.edit
listdir = _fs.listdir
exists = _fs.exists


class Sandbox:
    """Convenience facade over the sandbox modules."""

    distro = base.DISTRO
    user = base.USER
    workdir = base.WORKDIR

    # lifecycle
    start = staticmethod(session.start)
    stop = staticmethod(session.stop)
    restart = staticmethod(session.restart)
    ensure = staticmethod(session.ensure)
    running = staticmethod(session.is_running)
    status = staticmethod(session.status)

    # exec + fs
    shell = staticmethod(_exec.shell)
    check = staticmethod(_exec.check)
    which = staticmethod(_exec.which)
    version = staticmethod(_exec.version)
    read = staticmethod(_fs.read)
    read_text = staticmethod(_fs.read_text)
    write = staticmethod(_fs.write)
    append = staticmethod(_fs.append)
    edit = staticmethod(_fs.edit)
    listdir = staticmethod(_fs.listdir)
    mkdir = staticmethod(_fs.mkdir)
    move = staticmethod(_fs.move)
    copy = staticmethod(_fs.copy)
    remove = staticmethod(_fs.remove)
    exists = staticmethod(_fs.exists)

    # packages + toolchains
    apt = staticmethod(pkg.apt_install)
    pip = staticmethod(pkg.pip_install)
    npm = staticmethod(pkg.npm_install)
    install_toolchain = staticmethod(toolchain.install)
    toolchains = staticmethod(toolchain.available)

    # info + resources
    info = staticmethod(health.info)
    versions = staticmethod(health.versions)
    snapshot = staticmethod(health.snapshot)
    resources = staticmethod(governor.summary)


sb = Sandbox()

__all__ = ["sb", "Sandbox", "base", "session", "health", "pkg",
           "toolchain", "governor", "shell", "read", "write"]
