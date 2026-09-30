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
AGENT_LABEL = "com.applygrid.menubar"


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


def lock_file() -> Path:
    return config.data_path().parent / "menubar.lock"


def acquire_lock():
    """Hold an exclusive lock for the life of the process, or None if taken.

    The pid file alone can't stop two copies: both check it, both see nothing,
    both start. That happened -- the login agent and a click on the app, four
    seconds apart. flock is atomic, and the kernel drops it when the process
    dies, so a crash can't leave it stuck.
    """
    import fcntl
    path = lock_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "w")
    except OSError:
        return object()       # can't lock at all: don't refuse to run
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle             # keep a reference, or the lock goes with it


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
