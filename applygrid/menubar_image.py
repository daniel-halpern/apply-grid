"""The menu bar sparkline, drawn rather than typed.

It used to be Block Elements characters (▁▂▄▆█). The menu bar's font gives
those uneven widths and baselines, so tall bars ran together into one blob
and short ones sat at different heights. Drawn bars share one baseline and
one width, and as a template image macOS tints them for a light or dark menu
bar, like any system icon.

Kept apart from render_menubar so the CLI and tests never import AppKit.
"""

from __future__ import annotations

BAR_W = 5.0       # points
GAP = 2.0
HEIGHT = 16.0     # the image; the menu bar centres it
BASE = 3.0        # bars stand on this line, level with the title's baseline
# Bar height per intensity level. Level 0 is a short stub rather than nothing,
# so the seven days stay countable when most of them are empty.
LEVEL_H = (1.5, 4.0, 6.5, 9.0, 11.5)
EMPTY_ALPHA = 0.35


def bars(levels: list[int]):
    """An NSImage of one bar per day, oldest first."""
    from AppKit import NSBezierPath, NSColor, NSImage, NSMakeRect

    width = len(levels) * BAR_W + (len(levels) - 1) * GAP

    def draw(_rect):
        for i, level in enumerate(levels):
            x = i * (BAR_W + GAP)
            alpha = EMPTY_ALPHA if level == 0 else 1.0
            NSColor.colorWithWhite_alpha_(0.0, alpha).setFill()
            rect = NSMakeRect(x, BASE, BAR_W, LEVEL_H[level])
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                rect, 1.0, 1.0).fill()
        return True

    # A drawing handler re-renders at whatever scale the display needs, so the
    # bars stay crisp on Retina and non-Retina screens alike.
    image = NSImage.imageWithSize_flipped_drawingHandler_(
        (width, HEIGHT), False, draw)
    image.setTemplate_(True)
    return image
