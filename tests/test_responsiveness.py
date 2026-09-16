"""Nothing on a click path may wait on the network.

A phone sync is a round trip to GitHub, ~800ms. It was once called inline from
button handlers in the settings and editor windows, and from `ja add`, so every
click froze for most of a second.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC = ROOT / "applygrid"

try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.withdraw()
    _probe.destroy()
    TK_OK = True
except Exception:  # noqa: BLE001
    TK_OK = False


class NoInlineSyncTest(unittest.TestCase):
    """Static check: the UI modules must go through the background Syncer."""

    def test_windows_never_call_sync_directly(self):
        for name in ("settings.py", "editor.py"):
            with self.subTest(module=name):
                body = (SRC / name).read_text()
                self.assertNotIn(
                    "publish.sync(", body,
                    f"{name} must use background.Syncer, not a blocking sync")
                self.assertIn("syncer.request()", body)

    # Anything that shells out or hits the network must not run on the menu
    # bar's own thread. Counting threads is brittle -- this counts blocking
    # call sites instead, so adding one without a thread fails.
    BLOCKING_CALLS = ("publish.sync(", "nudge.maybe_send(", "notify.send(")

    def test_every_blocking_menubar_call_has_a_thread(self):
        body = (SRC / "menubar.py").read_text()
        blocking = sum(body.count(call) for call in self.BLOCKING_CALLS)
        threads = body.count("threading.Thread")
        self.assertGreater(blocking, 0, "the call sites moved; update this test")
        self.assertGreaterEqual(
            threads, blocking,
            f"menubar.py has {blocking} blocking call(s) but only {threads} "
            f"thread(s) -- one of them runs on the UI thread")

    def test_each_blocking_call_sits_inside_a_worker(self):
        """A thread count alone wouldn't catch a call outside its worker."""
        body = (SRC / "menubar.py").read_text()
        for call in self.BLOCKING_CALLS:
            start = 0
            while True:
                at = body.find(call, start)
                if at == -1:
                    break
                start = at + 1
                # walk back to the enclosing def; it must be a nested worker
                before = body[:at]
                enclosing = before.rfind("        def run():")
                closer = before.rfind("\n    def ")
                self.assertGreater(
                    enclosing, closer,
                    f"{call} is not inside a worker function")

    def test_cli_logging_does_not_wait_on_the_network(self):
        body = (SRC / "cli.py").read_text()
        start = body.index("def _maybe_sync")
        end = body.index("def build_parser")
        handler = body[start:end]
        self.assertNotIn("publish.sync(", handler,
                         "`ja add` must not block on a sync")
        self.assertIn("start_new_session=True", handler,
                      "the detached sync must outlive the CLI process")


@unittest.skipUnless(TK_OK, "Tk cannot open a display here")
class SyncerTest(unittest.TestCase):
    def setUp(self):
        from applygrid import background
        self.background = background
        self.root = tk.Tk()
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["APPLYGRID_LOCAL_CONFIG"] = str(
            Path(self.tmp.name) / "local.json")
        os.environ["APPLYGRID_DATA"] = str(Path(self.tmp.name) / "e.jsonl")

    def tearDown(self):
        self.root.destroy()
        for key in ("APPLYGRID_LOCAL_CONFIG", "APPLYGRID_DATA"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def test_a_burst_of_requests_collapses_into_one(self):
        syncer = self.background.Syncer(self.root, debounce_ms=5000)
        for _ in range(10):
            syncer.request()
        self.assertIsNotNone(syncer._pending)
        # Debounced: still nothing running after ten clicks.
        self.assertFalse(syncer._running)

    def test_requesting_returns_immediately(self):
        syncer = self.background.Syncer(self.root, debounce_ms=5000)
        start = time.perf_counter()
        for _ in range(50):
            syncer.request()
        elapsed = (time.perf_counter() - start) * 1000
        self.assertLess(elapsed, 50,
                        f"50 requests took {elapsed:.0f}ms; must not block")

    def test_the_worker_reports_back_on_the_main_thread(self):
        from applygrid import publish
        seen = []
        syncer = self.background.Syncer(self.root, on_status=seen.append,
                                        debounce_ms=10)
        real = publish.sync
        publish.sync = lambda *a, **k: "fakegist"
        try:
            syncer.request()
            deadline = time.time() + 5
            while not seen and time.time() < deadline:
                self.root.update()
                time.sleep(0.05)
        finally:
            publish.sync = real
        self.assertEqual(seen, ["phone synced"])

    def test_a_worker_failure_never_escapes(self):
        from applygrid import publish
        seen = []
        syncer = self.background.Syncer(self.root, on_status=seen.append,
                                        debounce_ms=10)
        real = publish.sync

        def boom(*_a, **_k):
            raise RuntimeError("network on fire")

        publish.sync = boom
        try:
            syncer.request()
            deadline = time.time() + 5
            while not seen and time.time() < deadline:
                self.root.update()
                time.sleep(0.05)
        finally:
            publish.sync = real
        self.assertTrue(seen and "failed" in seen[0], seen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
