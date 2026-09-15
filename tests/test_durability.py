"""Crash safety.

Every write must be on disk before the call returns, because the only thing
that persists is the event log -- nothing is held in memory waiting to be
"saved", so a crash must never cost more than the action in flight.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from applygrid import events  # noqa: E402


class FsyncTest(unittest.TestCase):
    """The calls that make a write survive power loss."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "events.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_fsyncs_before_returning(self):
        seen = []
        real = os.fsync
        os.fsync = lambda fd: (seen.append(fd), real(fd))[1]
        try:
            events.append({"ts": events.now_iso(), "kind": "prep"}, self.path)
        finally:
            os.fsync = real
        self.assertTrue(seen, "append returned without fsync")

    def test_rewrite_fsyncs_the_file_and_the_directory(self):
        """An atomic rename alone is not enough.

        The rename can reach disk before the data blocks, leaving a file that
        exists but is empty or short.
        """
        for i in range(3):
            events.append({"ts": events.now_iso(), "kind": "prep", "n": i},
                          self.path)
        seen = []
        real = os.fsync
        os.fsync = lambda fd: (seen.append(fd), real(fd))[1]
        try:
            events.remove_indices({0}, self.path)
        finally:
            os.fsync = real
        # one for the temp file, one for the directory entry
        self.assertGreaterEqual(len(seen), 2,
                                "rewrite must fsync the file and its directory")

    def test_rewrite_leaves_no_temp_file_behind(self):
        events.append({"ts": events.now_iso(), "kind": "prep"}, self.path)
        events.remove_indices({0}, self.path)
        strays = list(self.path.parent.glob("*.tmp"))
        self.assertEqual(strays, [])


class SigkillTest(unittest.TestCase):
    """Kill writers outright and check the log is still parseable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "events.jsonl"
        self.env = dict(os.environ, APPLYGRID_DATA=str(self.path),
                        APPLYGRID_LOCAL_CONFIG=str(
                            self.path.parent / "config.local.json"),
                        PYTHONPATH=str(ROOT))

    def tearDown(self):
        self.tmp.cleanup()

    def _kill_mid_write(self, program: str, rounds: int = 3) -> None:
        for _ in range(rounds):
            proc = subprocess.Popen([sys.executable, "-c", program],
                                    env=self.env,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            time.sleep(0.25)
            proc.send_signal(signal.SIGKILL)
            proc.wait()

    def _assert_every_line_parses(self) -> int:
        lines = [l for l in self.path.read_text().splitlines() if l.strip()]
        for number, line in enumerate(lines, 1):
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                self.fail(f"line {number} is corrupt after SIGKILL: "
                          f"{line[:60]!r} ({exc})")
        return len(lines)

    def test_appends_are_never_torn(self):
        self._kill_mid_write(
            "from applygrid import events\n"
            "while True: events.append({'ts': events.now_iso(),"
            " 'kind': 'prep'})\n")
        self.assertGreater(self._assert_every_line_parses(), 0)

    def test_rewrites_never_truncate_the_log(self):
        for i in range(600):
            events.append({"id": f"{i:04x}", "ts": events.now_iso(),
                           "kind": "application_quick", "company": f"Co{i}"},
                          self.path)
        seeded = len(events.read_lines(self.path))
        self._kill_mid_write(
            "import random\n"
            "from applygrid import events\n"
            "while events.read_lines():\n"
            "    events.remove_indices({random.randrange("
            "len(events.read_lines()))})\n")
        remaining = self._assert_every_line_parses()
        trash = events.trash_path(self.path)
        archived = len([l for l in trash.read_text().splitlines() if l.strip()]) \
            if trash.exists() else 0
        # A kill between archiving and rewriting duplicates a row rather than
        # dropping one, so the total can exceed the seed but never fall short.
        self.assertGreaterEqual(remaining + archived, seeded)


if __name__ == "__main__":
    unittest.main(verbosity=2)
