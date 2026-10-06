"""Text for the menu bar item and its dropdown.

macOS menus use a proportional font, so a 7-row grid would render ragged here.
Instead there's a sparkline: 7 days in the always-visible title, 30 in the
dropdown. The menu bar app draws it as an image (menubar_image.py); the Block
Elements text version here is the fallback, because the menu bar's font gives
those characters uneven widths and baselines. The full color grid lives on the desktop widget, the phone,
and the terminal, which can all render color properly.
"""

from __future__ import annotations

from datetime import timedelta

from .model import State

# Equal-width Block Elements, ascending. Index by intensity level 0-4.
SPARK = ("▁", "▂", "▄", "▆", "█")


def levels(state: State, days: int) -> list[int]:
    """Intensity level for each of the last `days` days, oldest first."""
    start = state.today - timedelta(days=days - 1)
    return [state.level(state.points_on(start + timedelta(days=i)))
            for i in range(days)]


def spark(state: State, days: int) -> str:
    """The same as text, for anywhere an image can't go."""
    return "".join(SPARK[level] for level in levels(state, days))


def title(state: State, show_spark: bool = True) -> str:
    """Short enough to live in a crowded menu bar."""
    bits = []
    if show_spark:
        bits.append(spark(state, 7))
    bits.append(f"{state.points_on(state.today)}/{state.target}")
    if state.streak_days:
        bits.append(f"·{state.streak_days}d")
    stale = len(state.stale())
    if stale:
        bits.append(f"·{stale}↻")
    return " ".join(bits)


SPARK_ROW = "last 30 days"


def header_lines(state: State, text_spark: bool = True) -> list[str]:
    """Disabled rows at the top of the dropdown -- the glanceable summary.

    With text_spark=False the sparkline row is just SPARK_ROW, for the menu
    bar app to draw the bars as an image beside it.
    """
    funnel = state.funnel
    offer_word = "offer" if funnel["offer"] == 1 else "offers"
    lines = [
        f"{state.points_on(state.today)}/{state.target} pts today"
        f"   ·   {state.week_to_date_points()}/{state.weekly_target} this week",
        f"{state.streak_days}d streak   ·   best {state.best_streak_days}d"
        f"   ·   {state.week_streak} weeks on target",
        "",
        f"{SPARK_ROW}  {spark(state, 30)}" if text_spark else SPARK_ROW,
        "",
        f"{funnel['applied']} applied  →  {funnel['screen']} "
        f"{'screen' if funnel['screen'] == 1 else 'screens'}"
        f"  →  {funnel['onsite']} "
        f"{'onsite' if funnel['onsite'] == 1 else 'onsites'}"
        f"  →  {funnel['offer']} {offer_word}",
        f"{len(state.live_apps) - len(state.cold_apps)} active"
        f"   ·   {len(state.cold_apps)} gone cold",
    ]
    lags = state.response_lags()
    if lags:
        mid = lags[len(lags) // 2]
        lines.append(f"typical reply comes back after {mid}d "
                     f"— a quiet week isn't a failed one")
    return lines
