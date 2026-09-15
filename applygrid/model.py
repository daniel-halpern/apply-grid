"""Fold the event log into everything the renderers need.

Pure functions over the event list -- no I/O -- so the whole thing is testable
against a fixture and cheap enough to run on shell startup.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import config, events as ev_mod


@dataclass
class Application:
    id: str
    company: str
    role: str
    source: str
    url: str
    kind: str
    applied_on: date
    stage: str = "applied"
    stage_idx: int = 0
    terminal: str = ""          # "rejected" / "withdrawn" / "" if still live
    last_event_on: date | None = None
    touches: int = 0            # follow-ups and other effort logged against it

    @property
    def is_live(self) -> bool:
        return not self.terminal and self.stage != "offer"

    def days_since_last_event(self, today: date) -> int:
        return (today - (self.last_event_on or self.applied_on)).days


@dataclass
class State:
    cfg: dict
    today: date
    daily_points: dict[date, int] = field(default_factory=dict)
    apps: dict[str, Application] = field(default_factory=dict)
    event_count: int = 0

    # -- points -------------------------------------------------------------
    def points_on(self, day: date) -> int:
        return self.daily_points.get(day, 0)

    @property
    def target(self) -> int:
        return self.cfg["daily_target"]

    @property
    def weekly_target(self) -> int:
        return self.target * self.cfg["weekly_target_multiplier"]

    # -- streaks ------------------------------------------------------------
    @property
    def streak_days(self) -> int:
        """Consecutive days with any effort, ending today.

        Today is forgiving: an empty morning doesn't zero the streak, because
        the day isn't over yet. The streak only breaks once a day has fully
        passed with nothing logged.
        """
        cursor = self.today
        if self.points_on(cursor) == 0:
            cursor -= timedelta(days=1)
        count = 0
        while self.points_on(cursor) > 0:
            count += 1
            cursor -= timedelta(days=1)
        return count

    @property
    def best_streak_days(self) -> int:
        active = sorted(d for d, p in self.daily_points.items() if p > 0)
        best = run = 0
        prev: date | None = None
        for day in active:
            run = run + 1 if prev and (day - prev).days == 1 else 1
            best = max(best, run)
            prev = day
        return best

    @property
    def week_streak(self) -> int:
        """Consecutive weeks hitting the weekly target.

        The headline streak for a job search, because daily streaks on
        emotionally heavy work break once and then get abandoned. The current
        week is forgiving in the same way today is.
        """
        start = _week_start(self.today)
        if self._week_points(start) < self.weekly_target:
            start -= timedelta(days=7)
        count = 0
        while self._week_points(start) >= self.weekly_target:
            count += 1
            start -= timedelta(days=7)
        return count

    def _week_points(self, start: date) -> int:
        return sum(self.points_on(start + timedelta(days=i)) for i in range(7))

    def week_to_date_points(self) -> int:
        start = _week_start(self.today)
        return sum(self.points_on(start + timedelta(days=i))
                   for i in range((self.today - start).days + 1))

    # -- pipeline -----------------------------------------------------------
    @property
    def funnel(self) -> dict[str, int]:
        """How many applications ever reached each stage."""
        counts = {stage: 0 for stage in config.STAGE_ORDER}
        for app in self.apps.values():
            for idx, stage in enumerate(config.STAGE_ORDER):
                if app.stage_idx >= idx:
                    counts[stage] += 1
        return counts

    @property
    def live_apps(self) -> list[Application]:
        return [a for a in self.apps.values() if a.is_live]

    def stale(self, days: int | None = None) -> list[Application]:
        """Live applications gone quiet recently enough to be worth chasing.

        Bounded at both ends on purpose. Without an upper bound every
        application you ever sent eventually lands here, and a nudge list that
        long is a wall of guilt you stop reading rather than a list of next
        actions. Past give_up_after_days it's cold, not owed a follow-up.
        """
        low = days if days is not None else self.cfg["stale_after_days"]
        high = self.cfg["give_up_after_days"]
        out = [a for a in self.live_apps
               if low <= a.days_since_last_event(self.today) <= high]
        out.sort(key=lambda a: a.days_since_last_event(self.today), reverse=True)
        return out

    @property
    def cold_apps(self) -> list[Application]:
        """Live in name only -- silent past the give-up window."""
        high = self.cfg["give_up_after_days"]
        return [a for a in self.live_apps
                if a.days_since_last_event(self.today) > high]

    @property
    def channels(self) -> list[tuple[str, int, int]]:
        """(source, applied, reached_screen_or_better), most applications first.

        Usually the most behaviour-changing number here: referrals tend to
        convert several times better than cold applications.
        """
        applied: dict[str, int] = defaultdict(int)
        advanced: dict[str, int] = defaultdict(int)
        for app in self.apps.values():
            applied[app.source] += 1
            if app.stage_idx >= 1:
                advanced[app.source] += 1
        rows = [(src, n, advanced[src]) for src, n in applied.items()]
        rows.sort(key=lambda r: (-r[1], r[0]))
        return rows

    def response_lags(self) -> list[int]:
        """Days from applying to the first response, per application."""
        return sorted(a.first_response_lag for a in self.apps.values()
                      if getattr(a, "first_response_lag", None) is not None)


def _week_start(day: date) -> date:
    """Sunday-anchored, matching GitHub's grid."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def build(raw_events: list[dict], cfg: dict | None = None,
          today: date | None = None) -> State:
    cfg = cfg or config.load()
    state = State(cfg=cfg, today=today or date.today())
    weights = cfg["weights"]
    daily: dict[date, int] = defaultdict(int)

    for event in raw_events:
        state.event_count += 1
        kind = event.get("kind", "")
        day = ev_mod.parse_ts(event["ts"]).date()

        # Effort earns points on the day it happened. Outcomes earn none.
        points = weights.get(kind, 0)
        if points:
            daily[day] += points

        if kind in config.APPLICATION_KINDS:
            app = Application(
                id=event.get("id") or "",
                company=event.get("company", "").strip() or "(unknown)",
                role=event.get("role", "").strip(),
                source=event.get("source", "").strip() or "cold",
                url=event.get("url", "").strip(),
                kind=kind,
                applied_on=day,
                last_event_on=day,
            )
            app.first_response_lag = None
            state.apps[app.id] = app
            continue

        app = state.apps.get(event.get("app_id", ""))
        if app is None:
            continue  # standalone effort (resume work, prep) or an unknown ref

        app.last_event_on = day
        if kind in config.STAGE_KINDS:
            idx = config.STAGE_ORDER.index(config.STAGE_KINDS[kind])
            if idx > app.stage_idx:
                app.stage_idx = idx
                app.stage = config.STAGE_ORDER[idx]
            if app.first_response_lag is None:
                app.first_response_lag = (day - app.applied_on).days
        elif kind in config.TERMINAL_KINDS:
            app.terminal = kind
        else:
            app.touches += 1

    state.daily_points = dict(daily)
    return state


def bucket(points: int, target: int) -> int:
    """Intensity level 0-4.

    Scaled to a personal daily target rather than to your own all-time maximum
    the way GitHub does it -- with a relative scale, one binge day makes every
    ordinary day look like a failure. Capped at 2x target for the same reason:
    a 15-application afternoon shouldn't set an unmatchable high-water mark.
    """
    if points <= 0:
        return 0
    ratio = points / target
    if ratio < 0.5:
        return 1
    if ratio < 1.0:
        return 2
    if ratio < 2.0:
        return 3
    return 4


@dataclass
class Cell:
    day: date
    points: int
    level: int


def grid(state: State, weeks: int = 53,
         anchor: str | None = None) -> list[list[Cell | None]]:
    """Columns of 7 days, oldest column first.

    Two layouts:

    "today" (default) -- the last cell is today, so the grid is a solid
    rectangle with no blanks anywhere. Rows still each hold one weekday, just
    rotated so today's weekday sits on the bottom row.

    "sunday" -- GitHub's layout: row 0 is Sunday and the rest of the current
    week comes back as None. Faithful to the original, but it leaves a ragged
    notch at the bottom right.
    """
    anchor = anchor or state.cfg.get("week_anchor", "today")

    if anchor == "today":
        total = 7 * weeks
        start = state.today - timedelta(days=total - 1)
        columns: list[list[Cell | None]] = []
        for col in range(weeks):
            column: list[Cell | None] = []
            for row in range(7):
                day = start + timedelta(days=7 * col + row)
                pts = state.points_on(day)
                column.append(Cell(day, pts, bucket(pts, state.target)))
            columns.append(column)
        return columns

    last_col = _week_start(state.today)
    first_col = last_col - timedelta(days=7 * (weeks - 1))
    columns = []
    for col in range(weeks):
        column = []
        for row in range(7):
            day = first_col + timedelta(days=7 * col + row)
            if day > state.today:
                column.append(None)
            else:
                pts = state.points_on(day)
                column.append(Cell(day, pts, bucket(pts, state.target)))
        columns.append(column)
    return columns


def weekday_labels(columns: list[list[Cell | None]],
                   every: int = 2) -> list[str]:
    """Row labels read off the grid itself, so they follow the rotation."""
    out = []
    for row in range(7):
        cell = next((col[row] for col in columns if col[row] is not None), None)
        if cell is None or row % every:
            out.append("")
        else:
            out.append(cell.day.strftime("%a"))
    return out


def month_labels(columns: list[list[Cell | None]]) -> dict[int, str]:
    """Column index -> month abbreviation, placed where a new month starts."""
    labels: dict[int, str] = {}
    seen: set[tuple[int, int]] = set()
    for idx, column in enumerate(columns):
        for cell in column:
            if cell is None:
                continue
            key = (cell.day.year, cell.day.month)
            if key not in seen:
                seen.add(key)
                if cell.day.day <= 7:
                    labels[idx] = cell.day.strftime("%b")
            break
    return labels
