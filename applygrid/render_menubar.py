"""Text for the menu bar item and its dropdown.

macOS menus use a proportional font, so a 7-row grid would render ragged here.
Instead this uses Block Elements characters, which share one advance width and
so line up: a 7-day sparkline in the always-visible title, and a longer strip
in the dropdown. The full color grid lives on the desktop widget, the phone,
and the terminal, which can all render color properly.
"""

from __future__ import annotations

from datetime import timedelta

from .model import State, bucket

# Equal-width Block Elements, ascending. Index by intensity level 0-4.
SPARK = ("▁", "▂", "▄", "▆", "█")


def spark(state: State, days: int) -> str:
    start = state.today - timedelta(days=days - 1)
    out = []
    for i in range(days):
        day = start + timedelta(days=i)
        out.append(SPARK[bucket(state.points_on(day), state.target)])
    return "".join(out)


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


def header_lines(state: State) -> list[str]:
    """Disabled rows at the top of the dropdown -- the glanceable summary."""
    funnel = state.funnel
    offer_word = "offer" if funnel["offer"] == 1 else "offers"
    lines = [
        f"{state.points_on(state.today)}/{state.target} pts today"
        f"   ·   {state.week_to_date_points()}/{state.weekly_target} this week",
        f"{state.streak_days}d streak   ·   best {state.best_streak_days}d"
        f"   ·   {state.week_streak} weeks on target",
        "",
        f"last 30 days  {spark(state, 30)}",
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
