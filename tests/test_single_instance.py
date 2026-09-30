"""Only one menu bar app, ever.

Two copies once ran side by side -- the login agent and a click on the app,
four seconds apart -- because each checked the pid file, saw nothing, and
started. The result was two identical items next to the clock.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from applygrid import process  # noqa: E402


class LockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["APPLYGRID_DATA"] = str(Path(self.tmp.name) / "events.jsonl")

    def tearDown(self):
        os.environ.pop("APPLYGRID_DATA", None)
        self.tmp.cleanup()

    def test_second_holder_is_refused(self):
        first = process.acquire_lock()
        self.assertIsNotNone(first)
        self.assertIsNone(process.acquire_lock())
        first.close()
        again = process.acquire_lock()
        self.assertIsNotNone(again)
        again.close()

    def test_lock_dies_with_its_process(self):
        """A crash must not leave the app unable to start."""
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "import time; from applygrid import process\n"
             "h = process.acquire_lock(); print('held', flush=True); "
             "time.sleep(60)"],
            env=dict(os.environ, PYTHONPATH=str(ROOT)),
            stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            self.assertIsNone(process.acquire_lock())
            holder.send_signal(signal.SIGKILL)
            holder.wait(timeout=5)
            time.sleep(0.1)
            lock = process.acquire_lock()
            self.assertIsNotNone(lock)
            lock.close()
        finally:
            if holder.poll() is None:
                holder.kill()
            holder.stdout.close()

    def test_menubar_does_not_start_when_locked(self):
        try:
            from applygrid import menubar
        except SystemExit:
            self.skipTest("rumps not installed for this interpreter")
        held = process.acquire_lock()
        try:
            with mock.patch.object(menubar, "ApplyGrid") as app:
                menubar.main()
            app.assert_not_called()
        finally:
            held.close()


class AgentTest(unittest.TestCase):
    def test_app_hands_off_to_the_agent(self):
        """The app must not start its own copy when the agent exists.

        It did, and got a second menu bar app beside the agent's -- and on
        macOS 26 the one it started had its menu bar item hidden.
        """
        src = (ROOT / "bin" / "app-launcher").read_text()
        handoff = src.index("launchctl kickstart")
        direct = src.index('exec "$PY" -m applygrid.menubar')
        self.assertLess(handoff, direct)
        self.assertIn("exit 0", src[handoff:direct])

    def test_restart_can_wait(self):
        """`ja restart` sleeps between attempts. A `from datetime import time`
        once replaced the time module and crashed it on the first sleep."""
        from applygrid import cli
        self.assertTrue(callable(getattr(cli.time, "sleep", None)))


if __name__ == "__main__":
    unittest.main()
