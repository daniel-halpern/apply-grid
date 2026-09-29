#!/usr/bin/env python3
"""Generate the app icon: a contribution grid on a dark squircle.

Writes the PNG by hand (zlib + struct, no Pillow) so the build needs nothing
installed, then lets macOS's own `sips` do the downscaling and `iconutil` build
the .icns.

Colours come from applygrid.palette, so the icon can't drift from the grids the
app actually draws. The brightest cell sits bottom-right, matching the default
grid layout where today is the last square.
"""

from __future__ import annotations

import math
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from applygrid import palette  # noqa: E402

SIZE = 1024
# Big Sur proportions: the squircle is inset, not full-bleed.
INSET = 100
RADIUS = 186
# Two designs. A 5x5 grid renders about 2px per cell at 16pt and collapses
# into a green blob, so the small sizes get a bolder 3x3 instead -- the same
# approach Apple takes by shipping distinct artwork per size in an iconset.
DETAILED = [
    [0, 0, 1, 0, 2],
    [0, 1, 0, 2, 3],
    [1, 0, 2, 3, 2],
    [0, 2, 3, 4, 3],
    [1, 3, 2, 3, 4],
]
SIMPLE = [
    [0, 1, 2],
    [1, 2, 3],
    [2, 3, 4],
]
# The simple one also fills more of the tile, since at 16pt every pixel counts.
FIELD_DETAILED = 0.62
FIELD_SIMPLE = 0.70


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def coverage(px: float, py: float, cx: float, cy: float,
             hw: float, hh: float, r: float) -> float:
    """Antialiased coverage of a rounded rect at a pixel centre.

    Signed distance to the shape, softened over one pixel -- cheaper and
    cleaner than supersampling a 4096px canvas in pure Python.
    """
    dx = max(abs(px - cx) - (hw - r), 0.0)
    dy = max(abs(py - cy) - (hh - r), 0.0)
    return min(max(0.5 - (math.hypot(dx, dy) - r), 0.0), 1.0)


def blend(buf: bytearray, x: int, y: int, colour, alpha: float) -> None:
    if alpha <= 0:
        return
    i = (y * SIZE + x) * 4
    src_a = buf[i + 3] / 255
    out_a = alpha + src_a * (1 - alpha)
    for c in range(3):
        src = buf[i + c] / 255
        out = (colour[c] / 255 * alpha + src * src_a * (1 - alpha)) / out_a
        buf[i + c] = max(0, min(255, round(out * 255)))
    buf[i + 3] = max(0, min(255, round(out_a * 255)))


def render(levels: list[list[int]], field_frac: float) -> bytearray:
    dark = palette.DARK
    grid = len(levels)
    buf = bytearray(SIZE * SIZE * 4)

    # 1. the squircle
    body = rgb(dark["surface"])
    cx = cy = SIZE / 2
    half = (SIZE - 2 * INSET) / 2
    lo, hi = INSET - 2, SIZE - INSET + 2
    for y in range(int(lo), int(hi)):
        for x in range(int(lo), int(hi)):
            a = coverage(x + 0.5, y + 0.5, cx, cy, half, half, RADIUS)
            if a:
                blend(buf, x, y, body, a)

    # 2. the cells
    field = (SIZE - 2 * INSET) * field_frac
    gap = field / (grid * 6)
    cell = (field - gap * (grid - 1)) / grid
    origin = (SIZE - field) / 2
    for row in range(grid):
        for col in range(grid):
            level = levels[row][col]
            colour = rgb(dark["empty"] if level == 0
                         else dark["levels"][level - 1])
            left = origin + col * (cell + gap)
            top = origin + row * (cell + gap)
            ccx, ccy = left + cell / 2, top + cell / 2
            r = cell * 0.24
            for y in range(int(top) - 2, int(top + cell) + 3):
                for x in range(int(left) - 2, int(left + cell) + 3):
                    if not (0 <= x < SIZE and 0 <= y < SIZE):
                        continue
                    a = coverage(x + 0.5, y + 0.5, ccx, ccy,
                                 cell / 2, cell / 2, r)
                    if a:
                        blend(buf, x, y, colour, a)
    return buf


def write_png(path: Path, buf: bytearray) -> None:
    raw = bytearray()
    stride = SIZE * 4
    for y in range(SIZE):
        raw.append(0)                       # filter type 0
        raw += buf[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def build_icns(detailed: Path, simple: Path, out: Path) -> None:
    iconset = out.with_suffix(".iconset")
    if iconset.exists():
        for stale in iconset.iterdir():
            stale.unlink()
    else:
        iconset.mkdir(parents=True)
    # sips resamples better than anything hand-rolled, and ships with macOS.
    # Anything rendering at 64px or below uses the bolder artwork.
    for size in (16, 32, 128, 256, 512):
        for scale, suffix in ((1, ""), (2, "@2x")):
            pixels = size * scale
            source = simple if pixels <= 64 else detailed
            name = f"icon_{size}x{size}{suffix}.png"
            subprocess.run(["sips", "-z", str(pixels), str(pixels),
                            str(source), "--out", str(iconset / name)],
                           check=True, capture_output=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
                   check=True)


if __name__ == "__main__":
    detailed = ROOT / "icon.png"
    simple = ROOT / "icon-small.png"
    write_png(detailed, render(DETAILED, FIELD_DETAILED))
    write_png(simple, render(SIMPLE, FIELD_SIMPLE))
    print(f"wrote {detailed.name} and {simple.name}")
    icns = ROOT / "AppIcon.icns"
    build_icns(detailed, simple, icns)
    print(f"wrote {icns.name} ({icns.stat().st_size // 1024} KB)")
