"""Terminal renderer: the grid as truecolor block characters.

Kept deliberately cheap -- this runs on every shell startup, so it does no I/O
beyond the one event-log read its caller already did.
"""

from __future__ import annotations

import shutil

from . import model, palette
from .model import State

BLOCK = "██"          # two full blocks read as a square at most sizes
GUTTER = 4                      # width of the weekday label column


def fit_weeks(requested: int | None = None, width: int | None = None) -> int:
    """How many weeks fit the terminal. Each column costs 2 columns of text."""
    if requested:
        return max(1, min(53, requested))
    width = width or shutil.get_terminal_size((80, 24)).columns
    return max(8, min(53, (width - GUTTER - 1) // 2))


def render(state: State, weeks: int | None = None, mode: str | None = None,
           legend: bool = True, summary: bool = True) -> str:
    sch = palette.scheme(mode)
    cols = model.grid(state, fit_weeks(weeks))
    labels = model.month_labels(cols)
    weekdays = model.weekday_labels(cols)
    muted = palette.fg(sch["muted"])
    ink = palette.fg(sch["ink"])
    out = []

    # Month labels, positioned over the column where each month begins.
    header = [" "] * (GUTTER + 2 * len(cols))
    for idx, name in labels.items():
        at = GUTTER + 2 * idx
        for offset, ch in enumerate(name):
            if at + offset < len(header):
                header[at + offset] = ch
    out.append(muted + "".join(header).rstrip() + palette.RESET)

    for row in range(7):
        line = [muted + weekdays[row].ljust(GUTTER) + palette.RESET]
        for col in cols:
            cell = col[row]
            if cell is None:
                line.append("  ")
                continue
            line.append(palette.fg(palette.hex_for(cell.level, mode)) + BLOCK
                        + palette.RESET)
        out.append("".join(line))

    if legend:
        swatches = "".join(
            palette.fg(palette.hex_for(lvl, mode)) + BLOCK + palette.RESET
            for lvl in range(5))
        out.append(f"{' ' * GUTTER}{muted}Less{palette.RESET}{swatches}"
                   f"{muted}More{palette.RESET}   {muted}"
                   f"target {state.target} pts/day{palette.RESET}")

    if summary:
        out.append(" " * GUTTER + summary_line(state, mode))
    return "\n".join(out)


def summary_line(state: State, mode: str | None = None) -> str:
    """The numbers, in text.

    Not decoration: the color ramp alone shouldn't be the only way to read the
    data, so every surface carries the values as text too.
    """
    sch = palette.scheme(mode)
    ink = palette.fg(sch["ink"])
    muted = palette.fg(sch["muted"])
    today = state.points_on(state.today)
    funnel = state.funnel
    stale = len(state.stale())

    def plural(n: int, word: str) -> str:
        return word if n == 1 else word + "s"

    parts = [
        f"{ink}{today}{palette.RESET}{muted}/{state.target} today{palette.RESET}",
        f"{ink}{state.streak_days}d{palette.RESET}{muted} streak{palette.RESET}",
        f"{ink}{funnel['applied']}{palette.RESET}{muted} applied{palette.RESET}",
        f"{ink}{funnel['screen']}{palette.RESET}{muted} "
        f"{plural(funnel['screen'], 'screen')}{palette.RESET}",
    ]
    if funnel["offer"]:
        parts.append(f"{ink}{funnel['offer']}{palette.RESET}{muted} "
                     f"{plural(funnel['offer'], 'offer')}{palette.RESET}")
    if stale:
        parts.append(f"{ink}{stale}{palette.RESET}{muted} to follow up{palette.RESET}")
    return f"{muted} · {palette.RESET}".join(parts)


def render_compact(state: State, weeks: int = 20, mode: str | None = None) -> str:
    """Shell-startup variant: no month header, no legend, just grid + numbers."""
    sch = palette.scheme(mode)
    cols = model.grid(state, fit_weeks(weeks))
    lines = []
    for row in range(7):
        line = [" " * 2]
        for col in cols:
            cell = col[row]
            line.append("  " if cell is None else
                        palette.fg(palette.hex_for(cell.level, mode)) + BLOCK
                        + palette.RESET)
        lines.append("".join(line))
    lines.append("  " + summary_line(state, mode))
    return "\n".join(lines)
