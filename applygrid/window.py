"""Shared window behaviour.

A window opened from the menu bar agent arrives behind whatever you were
looking at, because the agent isn't the active application. These windows are
always opened in response to a click, so they should come to the front.
"""

from __future__ import annotations

import tkinter as tk


def bring_to_front(root: tk.Tk, hold_ms: int = 300) -> None:
    """Raise, focus, and briefly pin the window above other apps.

    -topmost is dropped again after a moment: it gets the window in front of
    the app you were using, without leaving it permanently floating over
    everything afterwards.
    """
    try:
        # Make this process the active app, not just raise it within Tk.
        from AppKit import NSApplication
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:  # noqa: BLE001 - AppKit is a nicety, not a requirement
        pass
    root.lift()
    root.focus_force()
    try:
        root.attributes("-topmost", True)
        root.after(hold_ms, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass


def center(root: tk.Tk, width: int, height: int) -> None:
    """Place a new window in the middle of the screen rather than at 0,0."""
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 3)
    root.geometry(f"{width}x{height}+{x}+{y}")
