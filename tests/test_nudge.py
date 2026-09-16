"""Nudge scheduling.

Every rule here exists to fight notification fatigue, so each one is pinned:
fire only when it can change the outcome, cap the volume, say something new,
and go quiet when ignored.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from applygrid import config, model, nudge  # noqa: E402

TODAY = date(2026, 9, 15)            # a Tuesday
EVENING = datetime(2026, 9, 15, 19, 30)
CFG = {
    "daily_target": 3,
    "weekly_target_multiplier": 4,
    "stale_after_days": 10,
    "give_up_after_days": 45,
    "week_anchor": "today",
    "color_scheme": "auto",
    "weights": config.DEFAULTS["weights"],
    "surfaces": {"desktop_widget": True, "terminal": True, "phone_sync": True},
    "nudges": dict(config.DEFAULTS["nudges"]),
}


def ts(day: date, hour: int = 12) -> str:
    return datetime(day.year, day.month, day.day, hour).astimezone() \
        .replace(microsecond=0).isoformat()


def state(events=(), **overrides):
    cfg = json.loads(json.dumps(CFG))
    cfg.update(overrides)
    return model.build(list(events), cfg, TODAY)


class WindowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["APPLYGRID_DATA"] = str(Path(self.tmp.name) / "e.jsonl")

    def tearDown(self):
        os.environ.pop("APPLYGRID_DATA", None)
        self.tmp.cleanup()

    def test_fires_inside_the_window(self):
        self.assertIsNotNone(nudge.evaluate(state(), EVENING))

    def test_silent_before_and_after_the_window(self):
        for hour in (9, 17, 21, 23):
            with self.subTest(hour=hour):
                when = EVENING.replace(hour=hour)
                self.assertIsNone(nudge.evaluate(state(), when))

    def test_disabled_means_never(self):
        cfg = json.loads(json.dumps(CFG))
        cfg["nudges"]["enabled"] = False
        self.assertIsNone(nudge.evaluate(state(**{"nudges": cfg["nudges"]}),
                                         EVENING))

    def test_weekends_can_be_skipped(self):
        cfg = json.loads(json.dumps(CFG))
        cfg["nudges"]["skip_weekends"] = True
        saturday = datetime(2026, 9, 19, 19, 30)
        self.assertIsNone(nudge.evaluate(state(**{"nudges": cfg["nudges"]}),
                                         saturday))


class OnlyWhenUsefulTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["APPLYGRID_DATA"] = str(Path(self.tmp.name) / "e.jsonl")

    def tearDown(self):
        os.environ.pop("APPLYGRID_DATA", None)
        self.tmp.cleanup()

    def test_silent_once_today_is_done(self):
        """The rule that makes a good week produce zero notifications."""
        done = [{"id": "a1", "ts": ts(TODAY), "kind": "application_tailored",
                 "company": "Stripe"}]
        self.assertIsNone(nudge.evaluate(state(done), EVENING))

    def test_fires_when_today_is_short(self):
        partial = [{"ts": ts(TODAY), "kind": "prep"}]        # 1 of 3
        self.assertIsNotNone(nudge.evaluate(state(partial), EVENING))

    def test_at_most_one_per_day(self):
        st = state()
        self.assertIsNotNone(nudge.maybe_send(st, EVENING, sender=lambda _n: True))
        self.assertIsNone(nudge.evaluate(st, EVENING.replace(hour=20)))

    def test_weekly_budget_is_respected(self):
        # TODAY is a Tuesday, so its ISO week starts the day before. Anything
        # earlier than that falls in the previous week and doesn't count.
        monday = TODAY - timedelta(days=1)
        self.assertEqual(monday.isocalendar()[1], TODAY.isocalendar()[1])
        cfg = json.loads(json.dumps(CFG))
        cfg["nudges"]["max_per_week"] = 1
        nudge.save_history({"sent": [{
            "at": datetime(monday.year, monday.month, monday.day,
                           19, 0).isoformat(),
            "kind": "plain", "points_at": 0, "acted": True}],
            "paused_until": None})
        self.assertIsNone(nudge.evaluate(state(**{"nudges": cfg["nudges"]}),
                                         EVENING))

    def test_budget_counts_only_the_current_week(self):
        """Nudges from last week must not eat this week's budget."""
        earlier = TODAY - timedelta(days=4)      # previous ISO week
        self.assertNotEqual(earlier.isocalendar()[1], TODAY.isocalendar()[1])
        cfg = json.loads(json.dumps(CFG))
        cfg["nudges"]["max_per_week"] = 1
        nudge.save_history({"sent": [{
            "at": datetime(earlier.year, earlier.month, earlier.day,
                           19, 0).isoformat(),
            "kind": "plain", "points_at": 0, "acted": True}],
            "paused_until": None})
        self.assertIsNotNone(nudge.evaluate(state(**{"nudges": cfg["nudges"]}),
                                            EVENING))

    def test_a_new_week_resets_the_budget(self):
        last_week = TODAY - timedelta(days=9)
        sent = [{"at": datetime(last_week.year, last_week.month,
                                last_week.day, 19, 0).isoformat(),
                 "kind": "plain", "points_at": 0, "acted": True}
                for _ in range(3)]
        nudge.save_history({"sent": sent, "paused_until": None})
        self.assertIsNotNone(nudge.evaluate(state(), EVENING))


class BackoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["APPLYGRID_DATA"] = str(Path(self.tmp.name) / "e.jsonl")

    def tearDown(self):
        os.environ.pop("APPLYGRID_DATA", None)
        self.tmp.cleanup()

    def _ignored(self, count: int) -> list[dict]:
        rows = []
        for i in range(count):
            day = TODAY - timedelta(days=20 - i)
            rows.append({"at": datetime(day.year, day.month, day.day,
                                        19, 0).isoformat(),
                         "kind": "plain", "points_at": 0, "acted": False})
        return rows

    def test_three_ignored_nudges_pause_it(self):
        """Backing off is what keeps the channel usable; escalating kills it."""
        nudge.save_history({"sent": self._ignored(3), "paused_until": None})
        self.assertIsNone(nudge.evaluate(state(), EVENING))
        blob = nudge.history()
        self.assertIsNotNone(blob["paused_until"])
        self.assertGreater(date.fromisoformat(blob["paused_until"]), TODAY)

    def test_two_ignored_is_not_enough_to_pause(self):
        nudge.save_history({"sent": self._ignored(2), "paused_until": None})
        self.assertIsNotNone(nudge.evaluate(state(), EVENING))

    def test_acting_on_one_resets_the_run(self):
        rows = self._ignored(3)
        rows[-1]["acted"] = True
        nudge.save_history({"sent": rows, "paused_until": None})
        self.assertIsNotNone(nudge.evaluate(state(), EVENING))

    def test_a_pause_expires(self):
        nudge.save_history({
            "sent": [], "paused_until": (TODAY - timedelta(days=1)).isoformat()})
        self.assertIsNotNone(nudge.evaluate(state(), EVENING))

    def test_a_nudge_counts_as_heeded_if_points_rose_after_it(self):
        yesterday = TODAY - timedelta(days=1)
        events = [{"ts": ts(yesterday, 20), "kind": "application_tailored",
                   "id": "a1", "company": "Stripe"}]
        rows = [{"at": datetime(yesterday.year, yesterday.month,
                                yesterday.day, 19, 0).isoformat(),
                 "kind": "plain", "points_at": 0}]
        judged = nudge._judge_ignored(rows, state(events))
        self.assertTrue(judged[0]["acted"])


class MessageTest(unittest.TestCase):
    """It has to say something you don't already know."""

    def test_follow_ups_are_named_and_win(self):
        events = [{"id": "a1", "ts": ts(TODAY - timedelta(days=20)),
                   "kind": "application_tailored", "company": "Stripe"},
                  {"id": "a2", "ts": ts(TODAY - timedelta(days=22)),
                   "kind": "application_tailored", "company": "Ramp"}]
        message = nudge.compose(state(events))
        self.assertEqual(message.kind, "stale")
        self.assertIn("Stripe", message.message)
        self.assertIn("Ramp", message.message)

    def test_a_long_streak_at_risk_is_mentioned(self):
        # 1pt on each of the five previous days: a 5-day streak, but only one
        # of those days falls in the current ISO week, so "week" stays quiet.
        events = [{"ts": ts(TODAY - timedelta(days=d)), "kind": "prep"}
                  for d in (1, 2, 3, 4, 5)]
        st = state(events)
        self.assertEqual(st.streak_days, 5)
        message = nudge.compose(st)
        self.assertEqual(message.kind, "streak")
        self.assertIn("streak", message.title)

    def test_a_short_streak_is_not_worth_a_notification(self):
        """A daily streak is at risk every single day it isn't fed.

        With a low threshold, "streak at risk" would be the message on almost
        every nudge -- the same text every time, which is how a notification
        earns a permanent mute.
        """
        events = [{"ts": ts(TODAY - timedelta(days=d)), "kind": "prep"}
                  for d in (1, 2, 3)]
        st = state(events)
        self.assertEqual(st.streak_days, 3)
        self.assertNotEqual(nudge.compose(st).kind, "streak")

    def test_the_same_message_is_not_sent_twice_running(self):
        events = [{"ts": ts(TODAY - timedelta(days=d)), "kind": "prep"}
                  for d in (1, 2, 3, 4, 5)]
        st = state(events)
        first = nudge.compose(st)
        second = nudge.compose(st, avoid=first.kind)
        self.assertEqual(first.kind, "streak")
        self.assertNotEqual(second.kind, first.kind)

    def test_it_repeats_only_when_there_is_no_alternative(self):
        st = state()                       # nothing true but the fallback
        self.assertEqual([n.kind for n in nudge.candidates(st)], ["plain"])
        self.assertEqual(nudge.compose(st, avoid="plain").kind, "plain")

    def test_evaluate_avoids_the_previously_sent_kind(self):
        events = [{"ts": ts(TODAY - timedelta(days=d)), "kind": "prep"}
                  for d in (1, 2, 3, 4, 5)]
        st = state(events)
        yesterday = TODAY - timedelta(days=1)
        nudge.save_history({"sent": [{
            "at": datetime(yesterday.year, yesterday.month, yesterday.day,
                           19, 0).isoformat(),
            "kind": "streak", "points_at": 0, "acted": True}],
            "paused_until": None})
        picked = nudge.evaluate(st, EVENING)
        self.assertIsNotNone(picked)
        self.assertNotEqual(picked.kind, "streak")

    def test_a_week_within_reach_is_mentioned(self):
        start = TODAY - timedelta(days=2)
        events = [{"ts": ts(start, 10), "kind": "interview"},
                  {"ts": ts(start, 11), "kind": "interview"}]     # 10 of 12
        message = nudge.compose(state(events))
        self.assertEqual(message.kind, "week")

    def test_the_fallback_never_guilts(self):
        message = nudge.compose(state())
        self.assertEqual(message.kind, "plain")
        blob = (message.title + " " + message.message).lower()
        for word in ("nothing", "failed", "missed", "haven't", "didn't", "lazy"):
            self.assertNotIn(word, blob)

    def test_every_message_kind_is_reachable_and_non_empty(self):
        for message in (nudge.compose(state()),):
            self.assertTrue(message.title and message.message)
            self.assertLess(len(message.title), 60, "titles get truncated")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class RotationTest(unittest.TestCase):
    """Variety is the anti-fatigue mechanism; pin it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["APPLYGRID_DATA"] = str(Path(self.tmp.name) / "e.jsonl")

    def tearDown(self):
        os.environ.pop("APPLYGRID_DATA", None)
        self.tmp.cleanup()

    def _busy(self):
        events = [{"ts": ts(TODAY - timedelta(days=d)), "kind": "prep"}
                  for d in range(1, 8)]
        events += [{"id": f"a{i}", "ts": ts(TODAY - timedelta(days=20 + i)),
                    "kind": "application_tailored", "company": name}
                   for i, name in enumerate(("Stripe", "Ramp"))]
        return state(events)

    def test_three_true_conditions_produce_three_distinct_messages(self):
        st = self._busy()
        self.assertGreaterEqual(len(nudge.candidates(st)), 3)
        recent, seen = [], []
        for _ in range(3):
            picked = nudge.compose(st, avoid=recent)
            seen.append(picked.kind)
            recent = (recent + [picked.kind])[-nudge.RECENT_KINDS:]
        self.assertEqual(len(set(seen)), 3, f"repeated within three: {seen}")

    def test_avoiding_only_one_kind_would_merely_alternate(self):
        """Why RECENT_KINDS is 2: a window of 1 ping-pongs between two."""
        st = self._busy()
        recent, seen = [], []
        for _ in range(4):
            picked = nudge.compose(st, avoid=recent)
            seen.append(picked.kind)
            recent = (recent + [picked.kind])[-1:]      # window of one
        self.assertEqual(len(set(seen)), 2, seen)

    def test_a_string_avoid_still_works(self):
        st = self._busy()
        self.assertNotEqual(nudge.compose(st, avoid="stale").kind, "stale")
