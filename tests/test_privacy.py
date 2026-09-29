"""Guards that make this repo safe to publish.

Each of these protects against a specific way personal data could end up on
GitHub. They're cheap; run them before making the repo public.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from applygrid import config  # noqa: E402


class TrackedFilesTest(unittest.TestCase):
    """Nothing personal may be tracked by git."""

    @classmethod
    def setUpClass(cls):
        out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                             capture_output=True, text=True)
        cls.tracked = out.stdout.split()

    def test_no_event_logs_tracked(self):
        offenders = [f for f in self.tracked if f.endswith(".jsonl")]
        self.assertEqual(offenders, [], f"event log is tracked: {offenders}")

    def test_no_local_config_tracked(self):
        self.assertNotIn("config.local.json", self.tracked)

    def test_no_data_directory_tracked(self):
        offenders = [f for f in self.tracked if f.startswith("data/")]
        self.assertEqual(offenders, [], f"data/ is tracked: {offenders}")

    def test_shared_config_has_no_gist_id(self):
        """The gist id is the phone widget's only access control."""
        blob = json.loads((ROOT / "config.json").read_text())
        self.assertNotIn("gist_id", blob)

    def test_gitignore_covers_the_sensitive_paths(self):
        ignored = (ROOT / ".gitignore").read_text()
        for entry in ("config.local.json", "data/"):
            self.assertIn(entry, ignored)


class DataLocationTest(unittest.TestCase):
    def test_default_log_lives_outside_the_repo(self):
        """So a `git add -A` can never pick it up."""
        if config.LEGACY_DATA.exists():
            self.skipTest("an in-repo log exists and is honoured for back-compat")
        self.assertNotIn(ROOT, config.data_path().parents)


class ConfigPrecedenceTest(unittest.TestCase):
    def test_local_overrides_shared(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "shared.json"
            local = Path(tmp) / "local.json"
            shared.write_text(json.dumps({"daily_target": 3,
                                          "weights": {"prep": 1}}))
            local.write_text(json.dumps({"daily_target": 9,
                                         "gist_id": "abc123",
                                         "weights": {"prep": 7}}))
            old = dict(os.environ)
            os.environ["APPLYGRID_CONFIG"] = str(shared)
            os.environ["APPLYGRID_LOCAL_CONFIG"] = str(local)
            try:
                cfg = config.load()
            finally:
                os.environ.clear()
                os.environ.update(old)
            self.assertEqual(cfg["daily_target"], 9)
            self.assertEqual(cfg["gist_id"], "abc123")
            self.assertEqual(cfg["weights"]["prep"], 7)

    def test_set_local_does_not_touch_shared_config(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "shared.json"
            local = Path(tmp) / "local.json"
            shared.write_text(json.dumps({"daily_target": 3}))
            old = dict(os.environ)
            os.environ["APPLYGRID_CONFIG"] = str(shared)
            os.environ["APPLYGRID_LOCAL_CONFIG"] = str(local)
            try:
                config.set_local("gist_id", "deadbeef")
            finally:
                os.environ.clear()
                os.environ.update(old)
            self.assertNotIn("gist_id", shared.read_text())
            self.assertIn("deadbeef", local.read_text())


class PayloadTest(unittest.TestCase):
    def test_sync_payload_carries_no_identifying_fields(self):
        from datetime import date
        from applygrid import model, publish
        cfg = config.load()
        events = [
            {"id": "a1", "ts": "2026-09-10T12:00:00-04:00",
             "kind": "application_tailored", "company": "Stripe",
             "role": "Backend SWE", "url": "https://example.com",
             "notes": "referred by X"},
        ]
        state = model.build(events, cfg, date(2026, 9, 15))
        blob = publish.payload(state)
        publish.assert_no_pii(blob)
        text = json.dumps(blob)
        for secret in ("Stripe", "Backend SWE", "example.com", "referred"):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestIsolationTest(unittest.TestCase):
    """Tests must never write to the real state directory.

    publish._record puts last-sync.json next to the *active* log, so a test
    that redirects the config but not the data path silently overwrites the
    real one -- which is exactly what happened: a "phone sync is switched off"
    result from a fixture landed in the live status file.
    """

    TEST_FILES = sorted((ROOT / "tests").glob("test_*.py"))

    def test_anything_that_can_write_state_redirects_the_data_path(self):
        """Only flag files that actually reach code which writes state."""
        writers = ("publish.sync(", "publish._record(", "events.append(",
                   "events.remove_indices(", "events.replace_index(",
                   "nudge.maybe_send(")
        offenders = []
        for path in self.TEST_FILES:
            body = path.read_text()
            if not any(call in body for call in writers):
                continue
            if "APPLYGRID_DATA" not in body:
                offenders.append(path.name)
        self.assertEqual(
            offenders, [],
            f"{offenders} exercise code that writes state without redirecting "
            f"APPLYGRID_DATA, so they would write to the real directory")

    def test_the_real_state_directory_is_untouched_by_the_suite(self):
        """Belt and braces: the live status file must not move during a run."""
        from applygrid import config as live_config
        real = Path("~/.local/share/apply-grid/last-sync.json").expanduser()
        if not real.exists():
            self.skipTest("no live status file on this machine")
        before = real.read_text()
        # exercise the skip path the way the leak originally happened
        import os
        import tempfile
        from datetime import date
        from applygrid import model, publish
        with tempfile.TemporaryDirectory() as tmp:
            keep = {k: os.environ.get(k)
                    for k in ("APPLYGRID_DATA", "APPLYGRID_LOCAL_CONFIG")}
            os.environ["APPLYGRID_DATA"] = str(Path(tmp) / "e.jsonl")
            os.environ["APPLYGRID_LOCAL_CONFIG"] = str(Path(tmp) / "c.json")
            Path(os.environ["APPLYGRID_LOCAL_CONFIG"]).write_text(
                json.dumps({"surfaces": {"phone_sync": False}}))
            try:
                publish.sync(model.build([], live_config.load(),
                                         date.today()), verbose=False)
            finally:
                for key, value in keep.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
        self.assertEqual(real.read_text(), before,
                         "the suite modified the live last-sync.json")
