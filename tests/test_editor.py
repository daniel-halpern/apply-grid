"""Editor window behaviour, driven without entering the Tk main loop.

Builds the real window, withdraws it, and pokes its widgets. Skipped where Tk
can't open a display.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from applygrid import config, events  # noqa: E402

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
    _root.destroy()
    TK_OK = True
except Exception:  # noqa: BLE001 - headless machines have no display
    TK_OK = False


@unittest.skipUnless(TK_OK, "Tk cannot open a display here")
class EditorTest(unittest.TestCase):
    def setUp(self):
        from applygrid import editor
        self.editor_mod = editor
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "events.jsonl"
        os.environ["APPLYGRID_DATA"] = str(self.path)
        rows = [
            {"id": "a1", "ts": "2026-09-10T09:00:00-04:00",
             "kind": "application_tailored", "company": "Strpie",
             "role": "Backend SWE", "source": "cold"},
            {"id": "a2", "ts": "2026-09-12T15:30:00-04:00",
             "kind": "application_quick", "company": "Ramp",
             "role": "ML Engineer", "source": "referral"},
            {"ts": "2026-09-13T11:00:00-04:00", "kind": "prep"},
            {"ts": "2026-09-14T10:00:00-04:00", "kind": "response_screen",
             "app_id": "a1"},
        ]
        for row in rows:
            events.append(row, self.path)
        self.root = tk.Tk()
        self.root.withdraw()
        self.ed = editor.Editor(self.root)

    def tearDown(self):
        self.root.destroy()
        os.environ.pop("APPLYGRID_DATA", None)
        self.tmp.cleanup()

    def _select(self, index: int):
        self.ed.tree.selection_set(str(index))
        self.ed.on_select()

    # -- listing ------------------------------------------------------------
    def test_lists_every_entry_newest_first(self):
        self.assertEqual(len(self.ed.rows), 4)
        ids = self.ed.tree.get_children()
        self.assertEqual(len(ids), 4)
        firsts = [self.ed.tree.item(i)["values"][0] for i in ids]
        self.assertIn("14 sep", firsts[0])
        self.assertIn("10 sep", firsts[-1])

    def test_sorting_toggles_direction(self):
        self.ed.sort_by("when")
        top = self.ed.tree.item(self.ed.tree.get_children()[0])["values"][0]
        self.assertIn("10 sep", top)

    def test_filter_narrows_and_reports_the_count(self):
        self.ed.filter_var.set("ramp")
        self.assertEqual(len(self.ed.tree.get_children()), 1)
        self.assertIn("1 of 4", self.ed.count_label.cget("text"))
        self.ed.filter_var.set("")
        self.assertEqual(len(self.ed.tree.get_children()), 4)

    def test_attached_events_borrow_the_company_name(self):
        """A screen event stores only app_id; the table must still name it."""
        row = next(r for r in self.ed.rows
                   if r.blob.get("kind") == "response_screen")
        values = self.ed.tree.item(str(row.index))["values"]
        self.assertEqual(values[2], "Strpie")

    # -- form ---------------------------------------------------------------
    def test_kind_shows_a_human_label_and_stores_a_key(self):
        self._select(0)
        self.assertEqual(self.ed.fields["kind"].get(), "Tailored application")
        self.ed.fields["kind"].set("Quick application")
        self.ed.save()
        row = next(r for r in self.ed.rows if r.index == 0)
        self.assertEqual(row.blob["kind"], "application_quick")

    def test_editing_persists_to_the_log(self):
        self._select(0)
        self.ed.fields["company"].set("Stripe")
        self.ed.save()
        self.assertEqual(self.ed.status.cget("text"), "Saved.")
        self.assertEqual(events.read(self.path)[0]["company"], "Stripe")

    def test_selection_survives_a_save(self):
        """Otherwise a second correction needs another click."""
        self._select(0)
        self.ed.fields["company"].set("Stripe")
        self.ed.save()
        self.assertIsNotNone(self.ed.selected)
        self.ed.fields["role"].set("Staff Engineer")
        self.ed.save()
        self.assertEqual(events.read(self.path)[0]["role"], "Staff Engineer")

    def test_timestamp_can_be_moved(self):
        self._select(0)
        self.ed.fields["date"].set("2026-09-01")
        self.ed.fields["time"].set("08:15")
        self.ed.save()
        stamp = events.parse_ts(events.read(self.path)[0]["ts"])
        self.assertEqual((stamp.date().isoformat(), stamp.hour, stamp.minute),
                         ("2026-09-01", 8, 15))

    def test_unchanged_save_is_a_no_op(self):
        self._select(0)
        before = self.path.read_text()
        self.ed.save()
        self.assertEqual(self.ed.status.cget("text"), "No changes to save.")
        self.assertEqual(self.path.read_text(), before)

    # -- validation ---------------------------------------------------------
    def test_rejects_bad_input_without_writing(self):
        cases = [
            ({"date": "nonsense"}, "YYYY-MM-DD"),
            ({"date": "2030-01-01"}, "future"),
            ({"kind": "Nonsense"}, "Unknown kind"),
            ({"company": ""}, "needs a company"),
            ({"time": "99:99"}, "HH:MM"),
        ]
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                self._select(0)
                before = self.path.read_text()
                for key, value in overrides.items():
                    self.ed.fields[key].set(value)
                self.ed.save()
                self.assertIn(expected, self.ed.status.cget("text"))
                self.assertEqual(self.path.read_text(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
