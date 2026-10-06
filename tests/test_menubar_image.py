"""The drawn menu bar sparkline."""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applygrid import config, model, render_menubar  # noqa: E402

TODAY = date(2026, 10, 6)


class LevelsTest(unittest.TestCase):
    def test_oldest_first_ending_today(self):
        state = model.State(cfg=dict(config.DEFAULTS), today=TODAY)
        state.daily_points = {TODAY: 8, TODAY - timedelta(days=6): 2}
        levels = render_menubar.levels(state, 7)
        self.assertEqual(len(levels), 7)
        self.assertEqual(levels[-1], 4)
        self.assertEqual(levels[1:6], [0] * 5)
        self.assertGreater(levels[0], 0)

    def test_text_fallback_matches_levels(self):
        state = model.State(cfg=dict(config.DEFAULTS), today=TODAY)
        state.daily_points = {TODAY: 8}
        self.assertEqual(render_menubar.spark(state, 3), "▁▁█")

    def test_title_can_leave_the_sparkline_to_the_image(self):
        state = model.State(cfg=dict(config.DEFAULTS), today=TODAY)
        self.assertFalse(any(c in render_menubar.title(state, show_spark=False)
                             for c in render_menubar.SPARK))


class ImageTest(unittest.TestCase):
    def setUp(self):
        try:
            import AppKit  # noqa: F401
        except ImportError:
            self.skipTest("AppKit not available to this interpreter")

    def test_one_bar_per_day_as_a_template(self):
        from applygrid import menubar_image as mi
        image = mi.bars([0, 1, 2, 3, 4, 0, 4])
        self.assertTrue(image.isTemplate(), "must tint with the menu bar")
        width, height = image.size()
        self.assertAlmostEqual(width, 7 * mi.BAR_W + 6 * mi.GAP)
        self.assertEqual(height, mi.HEIGHT)

    def test_every_level_fits_inside_the_image(self):
        from applygrid import menubar_image as mi
        self.assertEqual(len(mi.LEVEL_H), 5)
        self.assertEqual(list(mi.LEVEL_H), sorted(mi.LEVEL_H))
        self.assertLessEqual(mi.BASE + max(mi.LEVEL_H), mi.HEIGHT)


if __name__ == "__main__":
    unittest.main()
