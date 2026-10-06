"""Settings, surface toggles, and the direction of the colour ramp."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from applygrid import config, palette  # noqa: E402


def luminance(hex_color: str) -> float:
    """WCAG relative luminance, for asserting which way a ramp runs."""
    parts = []
    for i in (1, 3, 5):
        channel = int(hex_color[i:i + 2], 16) / 255
        parts.append(channel / 12.92 if channel <= 0.03928
                     else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


class RampDirectionTest(unittest.TestCase):
    def test_light_ramp_darkens_as_activity_rises(self):
        """On a light surface, more effort must mean darker green."""
        levels = palette.LIGHT["levels"]
        lums = [luminance(h) for h in levels]
        self.assertEqual(lums, sorted(lums, reverse=True),
                         f"light ramp is not monotonically darkening: {levels}")
        self.assertLess(lums[-1], lums[0])

    def test_dark_ramp_brightens_as_activity_rises(self):
        """On a near-black surface it has to go the other way.

        Darker than the surface reads as absent, so the dark ramp brightens.
        """
        levels = palette.DARK["levels"]
        lums = [luminance(h) for h in levels]
        self.assertEqual(lums, sorted(lums),
                         f"dark ramp is not monotonically brightening: {levels}")

    def test_empty_cell_is_never_confusable_with_level_one(self):
        """No closer than GitHub's own graph.

        The palette is GitHub's, whose faintest green is close to its empty
        square in luminance (1.23:1 light, 1.55:1 dark) and is told apart
        mostly by hue -- a known weakness, accepted for the look. This floor
        stops any future edit from making it worse.
        """
        def ratio(a, b):
            hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
            return (hi + 0.05) / (lo + 0.05)
        for name, sch in (("light", palette.LIGHT), ("dark", palette.DARK)):
            with self.subTest(mode=name):
                self.assertGreaterEqual(
                    ratio(sch["empty"], sch["levels"][0]), 1.2,
                    f"{name}: empty and level 1 are too close")


class SchemeSelectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.local = Path(self.tmp.name) / "local.json"
        os.environ["APPLYGRID_LOCAL_CONFIG"] = str(self.local)
        os.environ["APPLYGRID_DATA"] = str(Path(self.tmp.name) / "e.jsonl")
        os.environ.pop("APPLYGRID_MODE", None)

    def tearDown(self):
        os.environ.pop("APPLYGRID_LOCAL_CONFIG", None)
        os.environ.pop("APPLYGRID_DATA", None)
        self.tmp.cleanup()

    def test_pinned_scheme_is_honoured(self):
        self.local.write_text(json.dumps({"color_scheme": "light"}))
        self.assertEqual(palette.scheme()["levels"], palette.LIGHT["levels"])
        self.local.write_text(json.dumps({"color_scheme": "dark"}))
        self.assertEqual(palette.scheme()["levels"], palette.DARK["levels"])

    def test_explicit_argument_beats_the_setting(self):
        self.local.write_text(json.dumps({"color_scheme": "dark"}))
        self.assertEqual(palette.scheme("light")["levels"],
                         palette.LIGHT["levels"])

    def test_env_var_beats_the_setting(self):
        self.local.write_text(json.dumps({"color_scheme": "dark"}))
        os.environ["APPLYGRID_MODE"] = "light"
        try:
            self.assertEqual(palette.scheme()["levels"],
                             palette.LIGHT["levels"])
        finally:
            os.environ.pop("APPLYGRID_MODE", None)

    def test_scheme_travels_to_the_phone(self):
        from datetime import date
        from applygrid import model, publish
        self.local.write_text(json.dumps({"color_scheme": "light"}))
        state = model.build([], config.load(), date(2026, 9, 15))
        self.assertEqual(publish.payload(state)["scheme"], "light")


class SurfaceToggleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.local = Path(self.tmp.name) / "local.json"
        os.environ["APPLYGRID_LOCAL_CONFIG"] = str(self.local)
        # APPLYGRID_DATA too: publish._record writes last-sync.json next to
        # the active log, so without this a test overwrites the real one.
        os.environ["APPLYGRID_DATA"] = str(Path(self.tmp.name) / "e.jsonl")

    def tearDown(self):
        os.environ.pop("APPLYGRID_LOCAL_CONFIG", None)
        os.environ.pop("APPLYGRID_DATA", None)
        self.tmp.cleanup()

    def test_default_is_every_surface_on(self):
        self.local.write_text("{}")
        for name in ("desktop_widget", "terminal", "phone_sync"):
            self.assertTrue(config.surface_enabled(name))

    def test_disabling_the_desktop_widget_renders_nothing(self):
        from datetime import date
        from applygrid import model, render_html
        self.local.write_text(json.dumps(
            {"surfaces": {"desktop_widget": False}}))
        state = model.build([], config.load(), date(2026, 9, 15))
        self.assertEqual(render_html.render(state), "")
        self.local.write_text(json.dumps(
            {"surfaces": {"desktop_widget": True}}))
        state = model.build([], config.load(), date(2026, 9, 15))
        self.assertGreater(len(render_html.render(state)), 100)

    def test_disabling_phone_sync_stops_the_push(self):
        from datetime import date
        from applygrid import model, publish
        self.local.write_text(json.dumps(
            {"surfaces": {"phone_sync": False}, "gist_id": "deadbeef"}))
        state = model.build([], config.load(), date(2026, 9, 15))
        self.assertIsNone(publish.sync(state, verbose=False))

    def test_toggling_one_surface_leaves_the_others_alone(self):
        self.local.write_text(json.dumps(
            {"surfaces": {"terminal": False, "phone_sync": True}}))
        config.update_local({"surfaces": {"desktop_widget": False}})
        cfg = config.load()
        self.assertEqual(cfg["surfaces"],
                         {"desktop_widget": False, "terminal": False,
                          "phone_sync": True})

    def test_the_shell_fast_path_reads_the_same_setting(self):
        """ja-startup greps the config rather than starting Python."""
        script = (ROOT / "bin" / "ja-startup").read_text()
        self.assertIn('"terminal":false', script)
        self.assertIn("config.local.json", script)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class SyncGuardTest(unittest.TestCase):
    """Only the real log may publish.

    A test or fixture run points APPLYGRID_DATA elsewhere while still reading
    the real config, so any code path that syncs would push that data to the
    live gist. This is how test fixture aggregates once reached the phone.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.local = Path(self.tmp.name) / "local.json"
        self.local.write_text(json.dumps({"gist_id": "deadbeefdeadbeef"}))
        os.environ["APPLYGRID_LOCAL_CONFIG"] = str(self.local)
        self.log = Path(self.tmp.name) / "somewhere-else.jsonl"
        self.log.write_text("")
        os.environ["APPLYGRID_DATA"] = str(self.log)
        os.environ.pop("APPLYGRID_ALLOW_SYNC", None)

    def tearDown(self):
        for key in ("APPLYGRID_LOCAL_CONFIG", "APPLYGRID_DATA",
                    "APPLYGRID_ALLOW_SYNC"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _state(self):
        from datetime import date
        from applygrid import model
        return model.build([], config.load(), date(2026, 9, 15))

    def test_a_non_default_log_refuses_to_publish(self):
        from applygrid import publish
        self.assertIsNone(publish.sync(self._state(), verbose=False))

    def test_the_refusal_is_recorded_but_not_an_error(self):
        """Explained in the status file, without crying failure at the user."""
        from applygrid import publish
        publish.sync(self._state(), verbose=False)
        status = publish.last_status()
        self.assertIn("refusing to sync", status["detail"])
        self.assertTrue(status["skipped"])
        self.assertTrue(status["ok"], "a deliberate skip is not a failure")

    def test_an_explicit_override_is_respected(self):
        """Deliberate use stays possible; accidental use does not."""
        from applygrid import publish
        os.environ["APPLYGRID_ALLOW_SYNC"] = "1"
        # It gets past the guard and fails at gh instead, on the fake gist id.
        with self.assertRaises(SystemExit):
            publish.sync(self._state(), verbose=False)


try:
    import tkinter as _tk
    _probe = _tk.Tk()
    _probe.withdraw()
    _probe.destroy()
    TK_OK = True
except Exception:  # noqa: BLE001
    TK_OK = False


@unittest.skipUnless(TK_OK, "Tk cannot open a display here")
class SettingsWindowTest(unittest.TestCase):
    """Changes must apply on click.

    The first version put Save below the fold of a fixed-height,
    non-resizable window -- 770px of content in 620px -- so the button was
    unreachable and no setting appeared to work.
    """

    def setUp(self):
        import tkinter as tk
        from applygrid import settings
        self.tmp = tempfile.TemporaryDirectory()
        self.local = Path(self.tmp.name) / "local.json"
        self.local.write_text("{}")
        os.environ["APPLYGRID_LOCAL_CONFIG"] = str(self.local)
        os.environ["APPLYGRID_DATA"] = str(Path(self.tmp.name) / "events.jsonl")
        self.root = tk.Tk()
        self.root.withdraw()
        self.win = settings.Settings(self.root)

    def tearDown(self):
        self.root.destroy()
        for key in ("APPLYGRID_LOCAL_CONFIG", "APPLYGRID_DATA"):
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _saved(self) -> dict:
        return json.loads(self.local.read_text())

    def test_window_is_resizable_and_scrolls(self):
        self.assertEqual(self.root.resizable(), (1, 1))
        canvases = [w for w in self.root.winfo_children()
                    if w.winfo_children()]
        self.assertTrue(canvases, "content must live in a scrollable holder")

    def test_toggling_a_surface_writes_without_a_save_click(self):
        self.win.vars["surfaces.terminal"].set(False)
        self.win.apply()
        self.assertFalse(self._saved()["surfaces"]["terminal"])
        self.assertTrue(self._saved()["surfaces"]["phone_sync"],
                        "other surfaces must be left alone")

    def test_grid_layout_writes_without_a_save_click(self):
        self.win.vars["week_anchor"].set("sunday")
        self.win.apply()
        self.assertEqual(self._saved()["week_anchor"], "sunday")

    def test_colour_scheme_writes_without_a_save_click(self):
        self.win.vars["color_scheme"].set("light")
        self.win.apply()
        self.assertEqual(self._saved()["color_scheme"], "light")

    def test_usual_source_writes_without_a_save_click(self):
        self.win.vars["default_source"].set("university")
        self.win.apply()
        self.assertEqual(self._saved()["default_source"], "university")

    def test_unticked_efforts_are_hidden(self):
        self.win.vars["efforts.cold_outreach"].set(False)
        self.win.apply()
        self.assertEqual(self._saved()["hidden_efforts"], ["cold_outreach"])
        self.win.vars["efforts.cold_outreach"].set(True)
        self.win.apply()
        self.assertEqual(self._saved()["hidden_efforts"], [])

    def test_colour_scale_writes_without_a_save_click(self):
        self.win.vars["color_scale"].set("target")
        self.win.apply()
        self.assertEqual(self._saved()["color_scale"], "target")

    def test_targets_write_without_a_save_click(self):
        self.win.vars["daily_target"].set(7)
        self.win.apply()
        self.assertEqual(self._saved()["daily_target"], 7)

    def test_an_invalid_window_is_refused_and_nothing_is_written(self):
        self.win.vars["daily_target"].set(4)
        self.win.apply()
        before = self.local.read_text()
        self.win.vars["give_up_after_days"].set(3)
        self.win.vars["stale_after_days"].set(10)
        self.win.apply()
        self.assertIn("Cold", self.win.status.cget("text"))
        self.assertEqual(self.local.read_text(), before)

    def test_there_is_no_save_button_to_miss(self):
        def labels(widget):
            out = []
            for child in widget.winfo_children():
                text = ""
                try:
                    text = str(child.cget("text"))
                except Exception:  # noqa: BLE001
                    pass
                if text:
                    out.append(text)
                out.extend(labels(child))
            return out
        self.assertNotIn("Save", labels(self.root))
        self.assertIn("Close", labels(self.root))


class PeriodicSyncTest(unittest.TestCase):
    """A quiet day must still push.

    The payload embeds the date it was built from, so if nothing syncs on a day
    with no activity, the phone keeps drawing the grid as of the last day
    something was logged -- today lands on the wrong square.
    """

    def setUp(self):
        from datetime import datetime
        from applygrid import publish
        self.publish = publish
        self.now = datetime.fromisoformat("2026-09-18T19:00:00-04:00")

    def _status(self, at, ok=True, skipped=False):
        return {"at": at, "ok": ok, "skipped": skipped, "detail": ""}

    def test_due_when_nothing_has_ever_synced(self):
        self.assertTrue(self.publish.sync_due(None, self.now))
        self.assertTrue(self.publish.sync_due({}, self.now))

    def test_due_when_the_date_rolled_over(self):
        yesterday = self._status("2026-09-17T23:59:00-04:00")
        self.assertTrue(self.publish.sync_due(yesterday, self.now))

    def test_not_due_right_after_a_success(self):
        recent = self._status("2026-09-18T18:55:00-04:00")
        self.assertFalse(self.publish.sync_due(recent, self.now))

    def test_due_once_a_success_ages_out(self):
        old = self._status("2026-09-18T12:00:00-04:00")      # 7 hours
        self.assertTrue(self.publish.sync_due(old, self.now))

    def test_a_failure_retries_sooner_than_a_success(self):
        failed = self._status("2026-09-18T18:50:00-04:00", ok=False)
        self.assertFalse(self.publish.sync_due(failed, self.now))   # 10 min
        failed = self._status("2026-09-18T18:30:00-04:00", ok=False)
        self.assertTrue(self.publish.sync_due(failed, self.now))    # 30 min

    def test_a_deliberate_skip_is_not_a_failure(self):
        """Switched off or a fixture run shouldn't cause fast retries."""
        skipped = self._status("2026-09-18T18:50:00-04:00",
                               ok=True, skipped=True)
        self.assertFalse(self.publish.sync_due(skipped, self.now))

    def test_a_corrupt_timestamp_forces_a_sync(self):
        self.assertTrue(self.publish.sync_due({"at": "not a date"}, self.now))
