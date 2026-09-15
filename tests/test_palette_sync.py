"""Guard against the phone widget's palette drifting from palette.py.

The Scriptable widget runs on the phone and can't import Python, so it carries
a copy of the ramp. This test fails if the copy stops matching.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from applygrid import palette  # noqa: E402

WIDGET = ROOT / "widgets" / "scriptable" / "apply-grid.js"


def js_ramp(mode: str) -> dict:
    """Pull the `dark:` / `light:` object literal out of the widget source."""
    src = WIDGET.read_text()
    block = re.search(rf"{mode}:\s*\{{(.+?)\}},\n", src, re.S)
    assert block, f"no {mode} ramp found in {WIDGET.name}"
    body = block.group(1)
    out = {}
    for key in ("surface", "empty", "ink", "muted"):
        m = re.search(rf'{key}:\s*"(#[0-9a-fA-F]{{6}})"', body)
        assert m, f"{mode}.{key} missing"
        out[key] = m.group(1)
    levels = re.search(r"levels:\s*\[(.+?)\]", body, re.S)
    assert levels, f"{mode}.levels missing"
    out["levels"] = re.findall(r'"(#[0-9a-fA-F]{6})"', levels.group(1))
    return out


class PaletteSyncTest(unittest.TestCase):
    def test_dark_matches(self):
        self.assertEqual(js_ramp("dark"), palette.DARK)

    def test_light_matches(self):
        self.assertEqual(js_ramp("light"), palette.LIGHT)

    def test_four_levels_each(self):
        for mode in ("dark", "light"):
            self.assertEqual(len(js_ramp(mode)["levels"]), 4)


class HtmlWidgetTest(unittest.TestCase):
    def test_ubersicht_placeholders_present(self):
        """install.sh substitutes these; if renamed, the widget silently breaks."""
        src = (ROOT / "widgets" / "apply-grid.widget" / "index.jsx").read_text()
        self.assertIn("__APPLYGRID_BIN__", src)
        self.assertIn("__APPLYGRID_MODE__", src)
        installer = (ROOT / "install.sh").read_text()
        self.assertIn("__APPLYGRID_BIN__", installer)
        self.assertIn("__APPLYGRID_MODE__", installer)

    def test_scriptable_gist_placeholder_present(self):
        src = WIDGET.read_text()
        self.assertIn("__APPLYGRID_GIST_RAW__", src)
        cli_src = (ROOT / "applygrid" / "cli.py").read_text()
        self.assertIn("__APPLYGRID_GIST_RAW__", cli_src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
