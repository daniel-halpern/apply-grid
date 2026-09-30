"""Fold correctness, checked against hand-computed expectations.

Run: python3 -m unittest discover -s tests  (from the repo root)
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applygrid import config, model  # noqa: E402

TODAY = date(2026, 9, 15)          # a Tuesday
CFG = {
    "daily_target": 3,
    "weekly_target_multiplier": 4,
    "stale_after_days": 10,
    "give_up_after_days": 45,
    "weights": config.DEFAULTS["weights"],
}


def ts(day: date, hour: int = 12) -> str:
    return datetime.combine(day, time(hour)).astimezone() \
        .replace(microsecond=0).isoformat()


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


class PointsTest(unittest.TestCase):
    def test_weights_sum_per_day(self):
        state = model.build([
            {"id": "a1", "ts": ts(TODAY), "kind": "application_tailored",
             "company": "Stripe", "role": "SWE"},
            {"ts": ts(TODAY), "kind": "prep"},
            {"id": "a2", "ts": ts(TODAY), "kind": "application_quick",
             "company": "Ramp", "role": "SWE"},
        ], CFG, TODAY)
        self.assertEqual(state.points_on(TODAY), 3 + 1 + 1)

    def test_outcomes_earn_no_points(self):
        """A rejection is not effort, and must not tint the day."""
        state = model.build([
            {"id": "a1", "ts": ts(days_ago(30)), "kind": "application_tailored",
             "company": "Stripe"},
            {"ts": ts(TODAY), "kind": "rejected", "app_id": "a1"},
        ], CFG, TODAY)
        self.assertEqual(state.points_on(TODAY), 0)
        self.assertEqual(model.bucket(state.points_on(TODAY), 3), 0)

    def test_bucket_thresholds_and_cap(self):
        b = lambda p: model.bucket(p, 3)
        self.assertEqual(b(0), 0)
        self.assertEqual(b(1), 1)          # 0.33x
        self.assertEqual(b(2), 2)          # 0.67x
        self.assertEqual(b(3), 3)          # exactly target
        self.assertEqual(b(5), 3)          # 1.67x
        self.assertEqual(b(6), 4)          # 2x
        # A binge cannot set an unmatchable high-water mark.
        self.assertEqual(b(60), b(6))


class StreakTest(unittest.TestCase):
    def _state(self, active_offsets):
        evs = [{"ts": ts(days_ago(n)), "kind": "prep"} for n in active_offsets]
        return model.build(evs, CFG, TODAY)

    def test_counts_consecutive_days(self):
        self.assertEqual(self._state([0, 1, 2, 3]).streak_days, 4)

    def test_today_is_forgiving(self):
        """An empty morning must not zero a live streak."""
        self.assertEqual(self._state([1, 2, 3]).streak_days, 3)

    def test_breaks_after_a_full_empty_day(self):
        self.assertEqual(self._state([2, 3, 4]).streak_days, 0)

    def test_best_streak_scans_history(self):
        state = self._state([20, 21, 22, 23, 24, 1])
        self.assertEqual(state.best_streak_days, 5)

    def test_week_streak_needs_weekly_target(self):
        # weekly target = 3 * 4 = 12 pts. Five tailored applications = 15.
        evs = []
        for week in range(3):
            for day in range(5):
                offset = 7 * week + day
                evs.append({"id": f"w{week}{day}", "ts": ts(days_ago(offset)),
                            "kind": "application_tailored", "company": "X"})
        self.assertGreaterEqual(model.build(evs, CFG, TODAY).week_streak, 2)


class PipelineTest(unittest.TestCase):
    def _app(self, ident, offset, company="Stripe", source="cold"):
        return {"id": ident, "ts": ts(days_ago(offset)),
                "kind": "application_tailored", "company": company,
                "role": "SWE", "source": source}

    def test_funnel_is_cumulative(self):
        """Reaching onsite counts at every earlier stage too."""
        state = model.build([
            self._app("a1", 40),
            {"ts": ts(days_ago(30)), "kind": "response_screen", "app_id": "a1"},
            {"ts": ts(days_ago(20)), "kind": "response_technical", "app_id": "a1"},
            {"ts": ts(days_ago(10)), "kind": "response_onsite", "app_id": "a1"},
            self._app("a2", 30),
        ], CFG, TODAY)
        f = state.funnel
        self.assertEqual((f["applied"], f["screen"], f["technical"],
                          f["onsite"], f["offer"]), (2, 1, 1, 1, 0))

    def test_stage_never_regresses(self):
        state = model.build([
            self._app("a1", 40),
            {"ts": ts(days_ago(20)), "kind": "response_onsite", "app_id": "a1"},
            {"ts": ts(days_ago(10)), "kind": "response_screen", "app_id": "a1"},
        ], CFG, TODAY)
        self.assertEqual(state.apps["a1"].stage, "onsite")

    def test_first_response_lag(self):
        state = model.build([
            self._app("a1", 40),
            {"ts": ts(days_ago(25)), "kind": "response_screen", "app_id": "a1"},
            {"ts": ts(days_ago(5)), "kind": "response_technical", "app_id": "a1"},
        ], CFG, TODAY)
        self.assertEqual(state.apps["a1"].first_response_lag, 15)

    def test_channel_conversion(self):
        state = model.build([
            self._app("a1", 40, source="referral"),
            {"ts": ts(days_ago(30)), "kind": "response_screen", "app_id": "a1"},
            self._app("a2", 40, source="cold"),
            self._app("a3", 40, source="cold"),
        ], CFG, TODAY)
        by_src = {src: (n, adv) for src, n, adv in state.channels}
        self.assertEqual(by_src["referral"], (1, 1))
        self.assertEqual(by_src["cold"], (2, 0))


class StaleTest(unittest.TestCase):
    def _app(self, ident, offset):
        return {"id": ident, "ts": ts(days_ago(offset)),
                "kind": "application_tailored", "company": f"Co{ident}"}

    def test_window_is_bounded_at_both_ends(self):
        state = model.build([
            self._app("fresh", 3),     # too recent to chase
            self._app("due", 20),      # in the window
            self._app("cold", 90),     # past give-up: cold, not owed
        ], CFG, TODAY)
        self.assertEqual([a.id for a in state.stale()], ["due"])
        self.assertEqual([a.id for a in state.cold_apps], ["cold"])

    def test_terminal_and_offer_apps_are_not_chased(self):
        state = model.build([
            self._app("rej", 20),
            {"ts": ts(days_ago(19)), "kind": "rejected", "app_id": "rej"},
            self._app("won", 20),
            {"ts": ts(days_ago(19)), "kind": "offer", "app_id": "won"},
        ], CFG, TODAY)
        self.assertEqual(state.stale(), [])

    def test_a_followup_resets_the_clock(self):
        state = model.build([
            self._app("a1", 30),
            {"ts": ts(days_ago(2)), "kind": "follow_up", "app_id": "a1"},
        ], CFG, TODAY)
        self.assertEqual(state.stale(), [])


class GridTest(unittest.TestCase):
    """Two layouts, both pinned."""

    def _state(self):
        return model.build([], CFG, TODAY)

    def test_shape(self):
        for anchor in ("today", "sunday"):
            cols = model.grid(self._state(), 53, anchor=anchor)
            self.assertEqual(len(cols), 53)
            self.assertTrue(all(len(c) == 7 for c in cols))

    def test_today_anchor_is_a_solid_rectangle_ending_today(self):
        """The default: no blank cells, today in the bottom-right corner."""
        cols = model.grid(self._state(), 53, anchor="today")
        blanks = [c for col in cols for c in col if c is None]
        self.assertEqual(blanks, [])
        self.assertEqual(cols[-1][6].day, TODAY)
        # contiguous days, oldest first
        flat = [c.day for col in cols for c in col]
        self.assertEqual(flat[-1], TODAY)
        self.assertEqual((flat[-1] - flat[0]).days, len(flat) - 1)

    def test_today_anchor_rows_still_hold_one_weekday_each(self):
        """Rotated, not scrambled -- a row must stay a single weekday."""
        cols = model.grid(self._state(), 53, anchor="today")
        for row in range(7):
            weekdays = {col[row].day.weekday() for col in cols}
            self.assertEqual(len(weekdays), 1)
        self.assertEqual(cols[-1][6].day.weekday(), TODAY.weekday())

    def test_sunday_anchor_matches_github(self):
        cols = model.grid(self._state(), 53, anchor="sunday")
        first = next(c for c in cols[0] if c is not None)
        self.assertEqual(first.day.weekday(), 6)          # Sunday
        last = [c for c in cols[-1] if c is not None]
        self.assertEqual(last[-1].day, TODAY)
        self.assertEqual(sum(1 for c in cols[-1] if c is None), 4)  # Wed-Sat

    def test_no_future_cells_in_either_layout(self):
        for anchor in ("today", "sunday"):
            for col in model.grid(self._state(), 53, anchor=anchor):
                for cell in col:
                    if cell is not None:
                        self.assertLessEqual(cell.day, TODAY)

    def test_anchor_defaults_from_config(self):
        state = model.build([], {**CFG, "week_anchor": "sunday"}, TODAY)
        self.assertTrue(any(c is None for col in model.grid(state, 53)
                            for c in col))
        state = model.build([], {**CFG, "week_anchor": "today"}, TODAY)
        self.assertFalse(any(c is None for col in model.grid(state, 53)
                             for c in col))

    def test_month_labels_land_on_month_starts(self):
        cols = model.grid(self._state(), 53)
        labels = model.month_labels(cols)
        self.assertTrue(labels)
        for idx, name in labels.items():
            week = [c for c in cols[idx] if c is not None]
            self.assertIn(name, [d.day.strftime("%b") for d in week])

    def test_weekday_labels_follow_the_rotation(self):
        cols = model.grid(self._state(), 53, anchor="today")
        labels = model.weekday_labels(cols)
        self.assertEqual(len(labels), 7)
        # the labelled rows must name the weekday actually on that row
        for row, name in enumerate(labels):
            if name:
                self.assertEqual(name, cols[0][row].day.strftime("%a"))
        # bottom row is today's weekday
        self.assertEqual(cols[0][6].day.strftime("%a"), TODAY.strftime("%a"))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class RelativeScaleTest(unittest.TestCase):
    """Colour against your own busy days, the way GitHub does it."""

    def _state(self, points_by_days_ago: dict[int, int], scale="relative"):
        state = model.State(cfg=dict(CFG, color_scale=scale), today=TODAY)
        state.daily_points = {days_ago(n): p
                              for n, p in points_by_days_ago.items()}
        return state

    def test_spreads_across_all_four_greens(self):
        """The real log that prompted this: target 1, days of 1-7 points.

        Against the target every active day was level 3 or 4 -- two shades.
        """
        days = {13: 1, 12: 1, 9: 2, 7: 1, 6: 1, 3: 7, 1: 6, 0: 2}
        state = self._state(days)
        self.assertEqual(state.scale_top, 7)
        levels = {p: state.level(p) for p in days.values()}
        self.assertEqual(levels, {1: 1, 2: 2, 6: 4, 7: 4})
        self.assertEqual(state.level(4), 3)
        self.assertEqual(state.level(0), 0)

        flat = self._state(days, scale="target")
        flat.cfg["daily_target"] = 1
        self.assertEqual({flat.level(p) for p in days.values()}, {3, 4})

    def test_one_huge_day_does_not_wash_out_the_rest(self):
        days = {n: 3 for n in range(1, 20)}
        days[0] = 40
        state = self._state(days)
        self.assertEqual(state.scale_top, 3)
        self.assertEqual(state.level(3), 4)
        self.assertEqual(state.level(40), 4)

    def test_only_the_past_year_counts(self):
        state = self._state({400: 50, 2: 4})
        self.assertEqual(state.scale_top, 4)

    def test_empty_log(self):
        state = self._state({})
        self.assertEqual(state.scale_top, 1)
        self.assertEqual(state.level(0), 0)

    def test_any_effort_is_visible(self):
        self.assertEqual(model.relative_bucket(1, 100), 1)
        self.assertEqual(model.relative_bucket(0, 100), 0)

    def test_target_setting_keeps_the_old_scale(self):
        state = self._state({0: 3}, scale="target")
        self.assertEqual(state.level(3), model.bucket(3, 3))
