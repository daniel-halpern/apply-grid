"""Removal and restore.

The log is append-only in normal use, but a typo you can't take back is worse
than a rewrite -- so removal exists, and must never lose data.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from applygrid import events  # noqa: E402


class RemovalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "events.jsonl"
        os.environ["APPLYGRID_DATA"] = str(self.path)
        self.rows = [
            {"id": "a1", "ts": "2026-09-10T12:00:00-04:00",
             "kind": "application_tailored", "company": "Stripe", "role": "SWE"},
            {"ts": "2026-09-11T12:00:00-04:00", "kind": "prep"},
            {"ts": "2026-09-12T12:00:00-04:00", "kind": "response_screen",
             "app_id": "a1"},
            {"id": "a2", "ts": "2026-09-13T12:00:00-04:00",
             "kind": "application_quick", "company": "Ramp", "role": "SWE"},
        ]
        for row in self.rows:
            events.append(row, self.path)

    def tearDown(self):
        os.environ.pop("APPLYGRID_DATA", None)
        self.tmp.cleanup()

    def test_read_lines_is_file_order_not_sorted(self):
        """Undo means 'the last thing I typed', not 'the latest date'."""
        events.append({"ts": "2020-01-01T12:00:00-04:00", "kind": "prep"},
                      self.path)
        last = json.loads(events.read_lines(self.path)[-1])
        self.assertEqual(last["ts"], "2020-01-01T12:00:00-04:00")
        self.assertEqual(events.read(self.path)[0]["ts"],
                         "2020-01-01T12:00:00-04:00")  # read() does sort

    def test_remove_last_leaves_the_rest_intact(self):
        gone = events.remove_indices({3}, self.path)
        self.assertEqual(len(gone), 1)
        self.assertEqual(gone[0]["company"], "Ramp")
        remaining = events.read(self.path)
        self.assertEqual(len(remaining), 3)
        self.assertNotIn("Ramp", self.path.read_text())

    def test_removed_events_are_kept_not_destroyed(self):
        events.remove_indices({0}, self.path)
        trash = events.trash_path(self.path)
        self.assertTrue(trash.exists())
        kept = [json.loads(l) for l in trash.read_text().splitlines() if l]
        self.assertEqual(kept[0]["company"], "Stripe")
        self.assertIn("_removed_at", kept[0])

    def test_remove_many_and_restore_the_whole_batch(self):
        events.remove_indices({0, 2}, self.path)
        self.assertEqual(len(events.read(self.path)), 2)
        back = events.restore_last(self.path)
        self.assertEqual(len(back), 2)
        self.assertEqual(len(events.read(self.path)), 4)
        # the restore marker must not survive into the log
        self.assertNotIn("_removed_at", self.path.read_text())

    def test_restore_only_returns_the_most_recent_batch(self):
        events.remove_indices({3}, self.path)          # batch 1: Ramp
        events.remove_indices({0}, self.path)          # batch 2: Stripe
        back = events.restore_last(self.path)
        self.assertEqual([r.get("company") for r in back], ["Stripe"])
        self.assertEqual(len(events.read(self.path)), 3)  # Ramp still gone

    def test_removing_nothing_is_a_no_op(self):
        before = self.path.read_text()
        self.assertEqual(events.remove_indices(set(), self.path), [])
        self.assertEqual(self.path.read_text(), before)

    def test_restore_with_empty_trash(self):
        self.assertEqual(events.restore_last(self.path), [])

    def test_log_stays_parseable_after_a_rewrite(self):
        events.remove_indices({1}, self.path)
        rows = events.read(self.path)          # raises if any line is bad
        self.assertEqual(len(rows), 3)
        self.assertFalse(self.path.with_name(self.path.name + ".tmp").exists())


class DescribeTest(unittest.TestCase):
    def test_names_company_and_role(self):
        row = {"ts": "2026-09-10T14:30:00-04:00",
               "kind": "application_tailored", "company": "Stripe",
               "role": "Backend SWE"}
        text = events.describe(row)
        self.assertIn("Stripe", text)
        self.assertIn("Backend SWE", text)
        self.assertIn("Tailored application", text)

    def test_falls_back_to_a_passed_company(self):
        row = {"ts": "2026-09-10T14:30:00-04:00", "kind": "follow_up",
               "app_id": "a1"}
        self.assertIn("Stripe", events.describe(row, "Stripe"))

    def test_standalone_effort_needs_no_company(self):
        row = {"ts": "2026-09-10T14:30:00-04:00", "kind": "prep"}
        self.assertIn("Interview prep", events.describe(row))


if __name__ == "__main__":
    unittest.main(verbosity=2)
