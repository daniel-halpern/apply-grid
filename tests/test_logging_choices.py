"""Where applications come from, and the online assessment effort."""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applygrid import cli, config, model  # noqa: E402

TODAY = date(2026, 10, 5)
CFG = dict(config.DEFAULTS, weights=dict(config.DEFAULTS["weights"]))


def ts(day: date) -> str:
    return datetime.combine(day, time(12)).astimezone().isoformat()


class SourceTagTest(unittest.TestCase):
    def test_no_tag_uses_your_usual_source(self):
        self.assertEqual(config.parse_source("Stripe / SWE", "linkedin"),
                         ("Stripe / SWE", "linkedin"))

    def test_tags_anywhere_any_case(self):
        self.assertEqual(config.parse_source("Stripe / SWE @Uni", "linkedin"),
                         ("Stripe / SWE", "university"))
        self.assertEqual(config.parse_source("@portal Ramp / SWE", "linkedin"),
                         ("Ramp / SWE", "portal"))

    def test_unknown_at_words_are_kept(self):
        """An @ in a company name must not vanish silently."""
        self.assertEqual(config.parse_source("AT@T / SWE", "linkedin"),
                         ("AT@T / SWE", "linkedin"))
        self.assertEqual(config.parse_source("Foo / SWE @nope", "linkedin"),
                         ("Foo / SWE @nope", "linkedin"))

    def test_every_tag_and_default_is_a_known_source(self):
        for tag, source in config.SOURCE_TAGS.items():
            self.assertIn(source, config.SOURCES, tag)
        self.assertIn(config.DEFAULTS["default_source"], config.SOURCES)

    def test_source_flag(self):
        self.assertEqual(cli._source_from("uni", "linkedin"), "university")
        self.assertEqual(cli._source_from("portal", "linkedin"), "portal")
        with self.assertRaises(SystemExit):
            cli._source_from("carrier-pigeon", "linkedin")


class OnlineAssessmentTest(unittest.TestCase):
    def _state(self, extra):
        return model.build([
            {"id": "a1", "ts": ts(TODAY - timedelta(days=6)),
             "kind": "application_quick", "company": "Doordash",
             "role": "SWE Intern", "source": "linkedin"},
        ] + extra, CFG, TODAY)

    def test_aliases(self):
        for word in ("oa", "OA", "assessment", "video", "hirevue"):
            self.assertEqual(cli.resolve_kind(word), "online_assessment")

    def test_worth_three_points(self):
        state = self._state([{"ts": ts(TODAY), "kind": "online_assessment",
                              "app_id": "a1"}])
        self.assertEqual(state.points_on(TODAY), 3)

    def test_marks_the_application_screened(self):
        """Being sent an OA is the company responding: no second entry."""
        state = self._state([{"ts": ts(TODAY), "kind": "online_assessment",
                              "app_id": "a1"}])
        app = state.apps["a1"]
        self.assertEqual(app.stage, "screen")
        self.assertEqual(app.first_response_lag, 6)
        self.assertEqual(state.funnel["screen"], 1)

    def test_never_moves_an_application_backwards(self):
        state = self._state([
            {"ts": ts(TODAY - timedelta(days=2)), "kind": "response_technical",
             "app_id": "a1"},
            {"ts": ts(TODAY), "kind": "online_assessment", "app_id": "a1"},
        ])
        self.assertEqual(state.apps["a1"].stage, "technical")

    def test_standalone_still_counts(self):
        state = self._state([{"ts": ts(TODAY), "kind": "online_assessment"}])
        self.assertEqual(state.points_on(TODAY), 3)
        self.assertEqual(state.apps["a1"].stage, "applied")


class EffortMenuTest(unittest.TestCase):
    def test_every_menu_effort_has_a_label_and_points(self):
        for kind in config.EFFORT_MENU:
            self.assertIn(kind, config.KIND_LABELS)
            self.assertGreater(config.DEFAULTS["weights"][kind], 0)


if __name__ == "__main__":
    unittest.main()
