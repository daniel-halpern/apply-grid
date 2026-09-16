"""Decide whether to nudge, and what to say.

Reminder features die of notification fatigue, and the cause is structural
rather than cosmetic: predictable timing, no new information, and firing when
you can't act. Better wording doesn't fix any of those. So:

* Only fire when it can change the outcome -- never once today's target is met.
  On a good week that means no notifications at all, and that scarcity is what
  keeps the channel worth reading.
* A weekly budget, so a bad week can't turn into a stream of pings.
* Say something you don't already know, picked from what is actually true --
  named follow-ups, a streak about to break, a week within reach. Rotating
  content habituates far more slowly than a fixed line.
* Back off when ignored. Three unheeded nudges pause it for a week; most tools
  escalate instead, which is how they get muted permanently.
* Never guilt. "You did nothing today" is the message that gets a tool deleted.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config
from .model import State


@dataclass
class Nudge:
    kind: str
    title: str
    message: str
    subtitle: str = "apply-grid"


def state_path() -> Path:
    return config.data_path().parent / "nudges.json"


def history() -> dict:
    try:
        return json.loads(state_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {"sent": [], "paused_until": None}


def save_history(blob: dict) -> None:
    try:
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(blob, indent=2) + "\n")
    except OSError:
        pass


def _week_key(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _judge_ignored(sent: list[dict], state: State) -> list[dict]:
    """Mark past nudges as heeded or not, once their day is over.

    A nudge counts as heeded if points rose on that day after it was sent.
    """
    for row in sent:
        if "acted" in row:
            continue
        when = datetime.fromisoformat(row["at"])
        if when.date() >= state.today:
            continue                      # today isn't over; no verdict yet
        row["acted"] = state.points_on(when.date()) > row.get("points_at", 0)
    return sent


def evaluate(state: State, now: datetime | None = None) -> Nudge | None:
    """The nudge to send right now, or None. Pure apart from reading history."""
    cfg = state.cfg
    settings = cfg.get("nudges", {})
    if not settings.get("enabled", True):
        return None

    now = now or datetime.now()
    blob = history()
    sent = _judge_ignored(blob.get("sent", []), state)

    paused = blob.get("paused_until")
    if paused and now.date() <= date.fromisoformat(paused):
        return None

    if settings.get("skip_weekends") and now.weekday() >= 5:
        return None

    start = int(settings.get("window_start_hour", 18))
    end = int(settings.get("window_end_hour", 21))
    if not start <= now.hour < end:
        return None

    # Nothing to ask for: today is already done.
    if state.points_on(state.today) >= state.target:
        return None

    # One per day, and a budget per week.
    if any(datetime.fromisoformat(r["at"]).date() == now.date() for r in sent):
        return None
    this_week = [r for r in sent
                 if _week_key(datetime.fromisoformat(r["at"]).date())
                 == _week_key(now.date())]
    if len(this_week) >= int(settings.get("max_per_week", 3)):
        return None

    # Ignored repeatedly? Go quiet rather than escalate.
    judged = [r for r in sent if "acted" in r]
    recent = judged[-int(settings.get("backoff_after_ignored", 3)):]
    if len(recent) == int(settings.get("backoff_after_ignored", 3)) \
            and all(not r["acted"] for r in recent):
        blob["paused_until"] = (
            now.date() + timedelta(days=int(settings.get("backoff_days", 7)))
        ).isoformat()
        blob["sent"] = sent
        save_history(blob)
        return None

    recent_kinds = [r["kind"] for r in sent[-RECENT_KINDS:]]
    return compose(state, avoid=recent_kinds)


# A daily streak is at risk on every day you haven't logged yet, which is
# exactly when a nudge fires -- so a low threshold would make "streak at risk"
# the message almost every time. Only mention it once it's genuinely worth
# protecting. (The forgiving measure the model actually headlines is the weekly
# streak; see State.week_streak.)
STREAK_FLOOR = 5


def candidates(state: State) -> list[Nudge]:
    """Every true thing worth saying, most actionable first.

    Points language only appears where it carries information -- a week within
    reach. It is never used to manufacture urgency, and the point weights are
    never recited: you already know them, so repeating them is exactly the kind
    of content-free reminder that gets muted.
    """
    out: list[Nudge] = []

    stale = state.stale()
    if stale:
        names = ", ".join(a.company for a in stale[:3])
        more = f" +{len(stale) - 3}" if len(stale) > 3 else ""
        quiet = stale[0].days_since_last_event(state.today)
        out.append(Nudge(
            "stale",
            f"{len(stale)} waiting on a follow-up",
            f"{names}{more} — quiet {quiet}+ days",
        ))

    if state.streak_days >= STREAK_FLOOR and state.points_on(state.today) == 0:
        out.append(Nudge(
            "streak",
            f"{state.streak_days}-day streak ends at midnight",
            "Anything logged today keeps it going",
        ))

    week_short = state.weekly_target - state.week_to_date_points()
    if 0 < week_short <= state.target:
        out.append(Nudge(
            "week",
            "Your week is within reach",
            f"{week_short} point{'s' if week_short != 1 else ''} hits "
            f"{state.weekly_target} for the week",
        ))

    lags = state.response_lags()
    if lags:
        weeks = max(1, lags[len(lags) // 2] // 7)
        out.append(Nudge(
            "lag",
            f"Today's applications reply in about {weeks} week"
            f"{'s' if weeks != 1 else ''}",
            "That's when your last few came back",
        ))

    # Nothing informative is true, so don't pretend otherwise: ask, rather
    # than quote a number or explain the scoring.
    out.append(Nudge(
        "plain",
        "apply-grid",
        state.cfg.get("nudges", {}).get(
            "fallback_message", "Anything worth applying to today?"),
        subtitle="",
    ))
    return out


# How many recent messages to avoid repeating. Two, not one: avoiding only the
# last kind makes a pair of true conditions alternate forever, which reads
# nearly as repetitive as no rotation at all.
RECENT_KINDS = 2


def compose(state: State, avoid: str | Iterable[str] | None = None) -> Nudge:
    """The best thing to say, preferring something not said recently.

    Without this, whichever condition ranks highest stays true for weeks and
    every notification reads identically -- the fastest route to being muted.
    """
    options = candidates(state)
    if avoid:
        recent = {avoid} if isinstance(avoid, str) else set(avoid)
        fresh = [n for n in options if n.kind not in recent]
        if fresh:
            return fresh[0]
    return options[0]


def maybe_send(state: State, now: datetime | None = None,
               sender=None) -> Nudge | None:
    """Evaluate and deliver. Returns the nudge sent, or None."""
    nudge = evaluate(state, now)
    if nudge is None:
        return None
    send = sender or _default_sender
    if not send(nudge):
        return None
    now = now or datetime.now()
    blob = history()
    blob.setdefault("sent", []).append({
        "at": now.replace(microsecond=0).isoformat(),
        "kind": nudge.kind,
        "points_at": state.points_on(state.today),
    })
    blob["sent"] = blob["sent"][-40:]       # keep the file small
    save_history(blob)
    return nudge


def _default_sender(nudge: Nudge) -> bool:
    from . import notify
    return notify.send(nudge.title, nudge.message, nudge.subtitle)
