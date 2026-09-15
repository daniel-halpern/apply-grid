"""Off-thread phone sync for Tk windows.

A sync is a network round trip to GitHub -- about 800ms. Calling it inline from
a button handler froze the window on every click, which is what made the
windows feel laggy.

Two things fix it: run it on a worker thread, and debounce, so a burst of
clicks results in one push instead of one per click. Results come back through
a queue drained by a Tk `after` poller, because Tk widgets may only be touched
from the thread running the main loop.
"""

from __future__ import annotations

import queue
import threading
from typing import Callable

DEBOUNCE_MS = 900
POLL_MS = 150


class Syncer:
    def __init__(self, root, on_status: Callable[[str], None] | None = None,
                 debounce_ms: int = DEBOUNCE_MS):
        self.root = root
        self.on_status = on_status
        self.debounce_ms = debounce_ms
        self._results: queue.Queue[str] = queue.Queue()
        self._pending = None          # scheduled `after` id
        self._running = False
        self._again = False           # a request arrived mid-flight
        self.root.after(POLL_MS, self._poll)

    def request(self) -> None:
        """Ask for a sync soon. Repeated calls collapse into one."""
        if self._pending is not None:
            self.root.after_cancel(self._pending)
        self._pending = self.root.after(self.debounce_ms, self._fire)

    def _fire(self) -> None:
        self._pending = None
        if self._running:
            self._again = True        # don't run two at once
            return
        self._running = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        message = ""
        try:
            from . import config, events, model, publish
            cfg = config.load()
            state = model.build(events.read(), cfg)
            pushed = publish.sync(state, verbose=False, quiet_fail=True)
            status = publish.last_status()
            if pushed:
                message = "phone synced"
            elif status and not status.get("ok") and not status.get("skipped"):
                message = f"phone sync failed: {status.get('detail', '?')}"
        except Exception as exc:  # noqa: BLE001 - never kill the window
            message = f"phone sync failed: {type(exc).__name__}"
        self._results.put(message)

    def _poll(self) -> None:
        try:
            while True:
                message = self._results.get_nowait()
                self._running = False
                if message and self.on_status:
                    self.on_status(message)
                if self._again:
                    self._again = False
                    self.request()
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._poll)
