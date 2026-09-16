"""Deliver a macOS notification.

osascript is the default because it works from an unbundled process, which is
how the menu bar app runs (`python -m applygrid.menubar`). rumps.notification
can be clickable, but silently does nothing unless the app is a packaged
bundle -- so it is only tried when explicitly asked for.
"""

from __future__ import annotations

import shutil
import subprocess


def _escape(text: str) -> str:
    """AppleScript string literals take backslash and quote escapes."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def send(title: str, message: str, subtitle: str = "") -> bool:
    osascript = shutil.which("osascript") or "/usr/bin/osascript"
    script = (f'display notification "{_escape(message)}" '
              f'with title "{_escape(title)}"')
    if subtitle:
        script += f' subtitle "{_escape(subtitle)}"'
    try:
        done = subprocess.run([osascript, "-e", script],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0
