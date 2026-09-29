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

    def test_geometry_fits_inside_every_box(self):
        """An oversized image gets scaled down and reads as too small."""
        import re
        src = WIDGET.read_text()
        block = re.search(r"const GEOMETRY = \{(.+?)\n\};", src, re.S).group(1)
        found = dict(
            (m.group(1), (int(m.group(2)), int(m.group(3)), int(m.group(4))))
            for m in re.finditer(
                r"(\w+):\s*\{\s*weeks:\s*(\d+),\s*cell:\s*(\d+),"
                r"\s*gap:\s*(\d+)", block))
        # iPhone Pro boxes minus this widget's own padding. The accessory
        # family uses setPadding(2, 4, 2, 4), not the desktop 12/13, so its
        # inner width is 160 - 8, not 160 - 26.
        inner = {"small": 158 - 26, "medium": 338 - 26, "large": 338 - 26,
                 "accessoryRectangular": 160 - 8}
        self.assertEqual(set(found), set(inner),
                         "a family is missing from GEOMETRY or from this test")
        for family, (weeks, cell, gap) in found.items():
            width = weeks * (cell + gap) - gap
            height = 7 * (cell + gap) - gap
            self.assertGreater(height, 0)
            self.assertLessEqual(width, inner[family],
                                 f"{family} grid is {width}pt in a "
                                 f"{inner[family]}pt box")
            # 0.88 rather than 0.9: medium sits at 91% and is deliberately
            # left alone, so the floor only has to catch a real mismatch like
            # the 43%-of-height large grid or an overflowing accessory slot.
            self.assertGreater(width / inner[family], 0.88,
                               f"{family} grid only fills "
                               f"{100 * width / inner[family]:.0f}% of its box")

    def test_a_stale_snapshot_still_advances_the_grid(self):
        """A sleeping Mac must not freeze the phone's grid on an old date.

        The payload carries the date it was built, so without a drift
        correction "today" points at the wrong square for as long as the Mac
        is asleep.
        """
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        script = r"""
        const fs = require("fs");
        // `node -e` shifts argv: the first extra argument lands at index 1.
        const src = fs.readFileSync(process.argv[1], "utf8");
        const body = src.slice(src.indexOf("function startOfDay"),
                               src.indexOf("function fillCell"));
        const m = new Function(body +
            "; return {driftDays, withDrift, levelsEndingToday};")();
        // Local components, not toISOString: that returns UTC, so late in
        // the evening in a western timezone it is already tomorrow and every
        // offset comes out one day short.
        const iso = (d) => `${d.getFullYear()}-` +
            `${String(d.getMonth() + 1).padStart(2, "0")}-` +
            `${String(d.getDate()).padStart(2, "0")}`;
        const day = (n) => { const d = new Date();
            d.setDate(d.getDate() - n); return iso(d); };
        const base = { levels: "0".repeat(369) + "31", today: day(2) };
        const drift = m.driftDays(base);
        const win = m.levelsEndingToday(m.withDrift(base, drift), 7);
        const fresh = m.driftDays({ levels: base.levels, today: day(0) });
        const future = m.driftDays({ levels: base.levels, today: "2099-01-01" });
        console.log(JSON.stringify({ drift, win, fresh, future }));
        """
        proc = subprocess.run([node, "-e", script, str(WIDGET)],
                              capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        got = json.loads(proc.stdout)
        self.assertEqual(got["drift"], 2, "two-day-old payload must drift by 2")
        # today unknown, and the snapshot's own day sits two places back
        self.assertEqual(got["win"][-1], "0")
        self.assertEqual(got["win"][-3], "1")
        self.assertEqual(got["win"][-4], "3")
        self.assertEqual(got["fresh"], 0, "a current payload must not shift")
        self.assertEqual(got["future"], 0, "a future date must clamp to 0")

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
