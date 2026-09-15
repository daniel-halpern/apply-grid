"""The one place colors are defined, so all four surfaces agree.

The ramp is a single-hue ordinal scale (OKLCH hue 142, four monotone lightness
steps) validated with the dataviz skill's `validate_palette.js --ordinal`:
monotone lightness, adjacent delta-L >= 0.06, light end >= 2:1 on its surface,
single hue. Both modes pass all four checks.

Deliberately NOT GitHub's own greens: theirs fail the light-end check
(#0e4429 is 1.69:1 on their dark surface, #9be9a8 is 1.44:1 on white), which is
why their faintest squares are so hard to tell from empty ones. Same look,
fixed floor.

Dark mode is its own set of steps validated against the dark surface, not an
inverted copy of the light ramp.
"""

from __future__ import annotations

import os

DARK = {
    "surface": "#0d1117",
    "empty": "#21262d",
    # level 1..4
    "levels": ["#0c7202", "#439d3b", "#70ca68", "#9ef994"],
    "ink": "#e6edf3",
    "muted": "#8b949e",
}

LIGHT = {
    "surface": "#ffffff",
    "empty": "#ebedf0",
    "levels": ["#62c958", "#4ab341", "#319c28", "#108604"],
    "ink": "#1f2328",
    "muted": "#636c76",
}


def scheme(mode: str | None = None) -> dict:
    """Pick a ramp.

    Precedence: an explicit argument, then APPLYGRID_MODE, then the
    color_scheme setting, then dark -- terminals can't be probed for their
    background, so dark is the fallback.

    In the light ramp darker green means more. The dark ramp brightens
    instead, because on a near-black surface "darker" tends toward invisible.
    """
    if not mode:
        mode = os.environ.get("APPLYGRID_MODE")
    if not mode:
        from . import config
        chosen = config.load().get("color_scheme", "auto")
        mode = None if chosen == "auto" else chosen
    mode = (mode or "dark").lower()
    return LIGHT if mode.startswith("l") else DARK


def hex_for(level: int, mode: str | None = None) -> str:
    """Cell fill for an intensity level 0-4."""
    sch = scheme(mode)
    if level <= 0:
        return sch["empty"]
    return sch["levels"][min(level, 4) - 1]


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def fg(hex_color: str) -> str:
    """Truecolor foreground escape."""
    r, g, b = rgb(hex_color)
    return f"\x1b[38;2;{r};{g};{b}m"


RESET = "\x1b[0m"
