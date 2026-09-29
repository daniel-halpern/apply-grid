"""Track whether the menu bar app is running.

Not via `pgrep -f applygrid.menubar`: that matches any process whose command
line merely contains the string -- a shell command, an editor, a grep -- so a
terminal window that mentioned the module name was enough to convince the
launcher the app was already up. A pid file plus a liveness check identifies
the actual process.
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from . import config

MARKER = "applygrid.menubar"


def pid_file() -> Path:
    return config.data_path().parent / "menubar.pid"


def _is_ours(pid: int) -> bool:
    """Alive, and actually the menu bar app rather than a recycled pid."""
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return MARKER in out.stdout


def running_pid() -> int | None:
    path = pid_file()
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        return None
    if _is_ours(pid):
        return pid
    try:                      # stale file from a crash or reboot
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def write_pid() -> None:
    path = pid_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{os.getpid()}\n")
    except OSError:
        pass


def clear_pid() -> None:
    try:
        pid_file().unlink(missing_ok=True)
    except OSError:
        pass


def stop() -> bool:
    """Ask a running instance to quit. True if one was signalled."""
    pid = running_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    return True
