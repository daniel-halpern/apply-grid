"""Exercise the phone widget in a stubbed Scriptable environment.

The iPhone widget is the only surface that can't be run from the Mac, so this
drives it through a stand-in for Scriptable's API and checks every widget
family builds and draws the right number of cells -- including the three
lock screen families, which were unhandled and silently fell through to the
medium geometry (286pt of grid into a ~160pt slot).

Skipped when node isn't installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HARNESS = ROOT / "tests" / "widget_harness.mjs"
WIDGET = ROOT / "widgets" / "scriptable" / "apply-grid.js"


def sample_payload() -> dict:
    """371 days of varied levels, so every ramp step gets drawn."""
    today = date(2026, 9, 15)
    levels = "".join(str(i % 5) for i in range(371))
    return {
        "v": 1, "anchor": "today",
        "start": (today - timedelta(days=370)).isoformat(),
        "today": today.isoformat(), "levels": levels,
        "target": 3, "weekly_target": 12, "today_points": 4,
        "week_points": 9, "streak_days": 5, "best_streak_days": 9,
        "week_streak": 2, "applied": 41, "screens": 7, "onsites": 2,
        "offers": 1, "active": 12, "stale": 3,
    }


class WidgetFamilyTest(unittest.TestCase):
    def test_every_family_builds_and_draws(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "payload.json"
            payload.write_text(json.dumps(sample_payload()))
            proc = subprocess.run(
                [node, str(HARNESS), str(WIDGET), str(payload)],
                capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(proc.returncode, 0,
                         f"widget harness failed:\n{proc.stdout}\n{proc.stderr}")
        for family in ("small", "medium", "large", "accessoryRectangular",
                       "accessoryCircular", "accessoryInline"):
            self.assertIn(family, proc.stdout)

    def test_lock_screen_families_are_handled_explicitly(self):
        """Not just present -- they must not fall through to a desktop size."""
        src = WIDGET.read_text()
        for family in ("accessoryRectangular", "accessoryCircular",
                       "accessoryInline"):
            self.assertIn(family, src)
        self.assertIn("MONO_ALPHA", src,
                      "lock screen is rendered monochrome; intensity needs an "
                      "alpha ramp, not hue")


if __name__ == "__main__":
    unittest.main(verbosity=2)
