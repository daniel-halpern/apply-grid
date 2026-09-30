"""Push an aggregate snapshot to a secret gist for the phone widget to read.

Privacy is the whole design constraint here. A secret gist's raw URL is
unguessable but unauthenticated -- anyone holding the URL can read it -- so the
payload carries only counts and intensity levels. No company names, no roles,
no URLs, no notes ever leave the machine.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from . import config
from .model import State

GIST_FILENAME = "applygrid.json"
HISTORY_DAYS = 371          # 53 weeks, what the widget can show at most


def payload(state: State) -> dict:
    """Aggregates only. Read this function before trusting the sync."""
    start = state.today - timedelta(days=HISTORY_DAYS - 1)
    levels = "".join(
        str(state.level(state.points_on(start + timedelta(days=i))))
        for i in range(HISTORY_DAYS))
    funnel = state.funnel
    return {
        "v": 1,
        "start": start.isoformat(),
        "today": state.today.isoformat(),
        # The phone must lay the grid out exactly like the Mac, so the layout
        # choice travels with the data rather than being duplicated as a
        # constant on both sides.
        "anchor": state.cfg.get("week_anchor", "today"),
        # "auto" lets the phone follow its own appearance; a pinned value wins,
        # so the light ramp (darker green = more) can be forced.
        "scheme": state.cfg.get("color_scheme", "auto"),
        "levels": levels,
        "target": state.target,
        "weekly_target": state.weekly_target,
        "today_points": state.points_on(state.today),
        "week_points": state.week_to_date_points(),
        "streak_days": state.streak_days,
        "best_streak_days": state.best_streak_days,
        "week_streak": state.week_streak,
        "applied": funnel["applied"],
        "screens": funnel["screen"],
        "onsites": funnel["onsite"],
        "offers": funnel["offer"],
        "active": len(state.live_apps) - len(state.cold_apps),
        "stale": len(state.stale()),
    }


SENSITIVE_KEYS = ("company", "role", "url", "notes", "id", "app_id")


def assert_no_pii(blob: dict) -> None:
    """Belt and braces: fail loudly rather than upload anything identifying."""
    text = json.dumps(blob)
    for key in SENSITIVE_KEYS:
        if f'"{key}"' in text:
            raise SystemExit(f"refusing to sync: payload contains {key!r}")


# launchd gives the menu bar app a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin),
# which does not include Homebrew -- so a bare "gh" was not found and the sync
# failed silently for anything logged from the menu bar. Resolve it explicitly.
GH_SEARCH_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"


def gh_binary() -> str:
    found = shutil.which("gh") or shutil.which("gh", path=GH_SEARCH_PATH)
    if not found:
        raise RuntimeError(
            "the `gh` CLI was not found. The menu bar app runs with a minimal "
            "PATH, so gh must be at one of: " + GH_SEARCH_PATH)
    return found


def _gh(*args: str) -> str:
    proc = subprocess.run((gh_binary(),) + args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gh failed")
    return proc.stdout.strip()


def status_path() -> Path:
    """Last sync outcome, so a failure can be surfaced instead of swallowed."""
    return config.data_path().parent / "last-sync.json"


def _record(ok: bool, detail: str = "", skipped: bool = False) -> None:
    """Record the last sync outcome.

    `skipped` marks a deliberate no-push -- switched off, or not the real log.
    Those keep ok=True so no surface reports a failure the user didn't cause,
    while the detail still says why nothing was sent.
    """
    try:
        path = status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "ok": ok,
            "skipped": skipped,
            "at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "detail": detail,
        }, indent=2) + "\n")
    except OSError:
        pass


SYNC_MAX_AGE_HOURS = 6
RETRY_AFTER_FAILURE_MINUTES = 15


def sync_due(status: dict | None, now: datetime,
             max_age_hours: int = SYNC_MAX_AGE_HOURS,
             retry_minutes: int = RETRY_AFTER_FAILURE_MINUTES) -> bool:
    """Should a periodic sync run?

    The payload embeds the date it was built, so a day with no activity still
    has to push -- otherwise the phone's grid freezes on the last day anything
    was logged. A failure retries sooner than a success, so a transient network
    problem doesn't cost the whole window.
    """
    if not status or not status.get("at"):
        return True
    try:
        when = datetime.fromisoformat(status["at"])
    except (TypeError, ValueError):
        return True
    if when.date() < now.date():
        return True                      # the date rolled over
    failed = not status.get("ok", True) and not status.get("skipped")
    window = (timedelta(minutes=retry_minutes) if failed
              else timedelta(hours=max_age_hours))
    return (now - when) >= window


def last_status() -> dict:
    try:
        return json.loads(status_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def sync(state: State, verbose: bool = True, quiet_fail: bool = False,
         init: bool = False) -> str | None:
    cfg = config.load()
    if not config.surface_enabled("phone_sync", cfg) and not init:
        _record(True, "phone sync is switched off in settings", skipped=True)
        if verbose:
            print("phone sync is switched off in settings")
        return None

    # Only the real log may publish. A test or a fixture run points
    # APPLYGRID_DATA somewhere else, and any code path that syncs would
    # otherwise push that data to the live gist -- which is exactly how test
    # fixture aggregates once reached the phone.
    active = config.data_path().resolve()
    allowed = {(config.DEFAULT_DATA_DIR / "events.jsonl").resolve()}
    if config.LEGACY_DATA.exists():
        allowed.add(config.LEGACY_DATA.resolve())
    if active not in allowed and os.environ.get("APPLYGRID_ALLOW_SYNC") != "1":
        message = (f"refusing to sync: the active log is {active}, not your "
                   f"real one. Set APPLYGRID_ALLOW_SYNC=1 to override.")
        _record(True, message, skipped=True)
        if verbose:
            print(message)
        return None
    blob = payload(state)
    assert_no_pii(blob)

    gist_id = cfg.get("gist_id")
    if not gist_id and not init:
        _record(True, "no gist configured - run `ja sync --init`", skipped=True)
        if verbose:
            print("no gist configured yet — run `ja sync --init` once to "
                  "create a secret gist for the phone widget")
        return None

    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / GIST_FILENAME
        local.write_text(json.dumps(blob, separators=(",", ":")) + "\n")
        try:
            if not gist_id:
                url = _gh("gist", "create", "--filename", GIST_FILENAME,
                          "--desc", "apply-grid aggregates (no identifying data)",
                          str(local))
                gist_id = url.rstrip("/").rsplit("/", 1)[-1]
                # Local-only: this id is the widget's access control.
                config.set_local("gist_id", gist_id)
                if verbose:
                    print(f"created secret gist {gist_id}")
            else:
                _gh("gist", "edit", gist_id, "--filename", GIST_FILENAME,
                    str(local))
        except (RuntimeError, OSError) as exc:
            _record(False, str(exc))
            if quiet_fail:
                return None
            raise SystemExit(f"gist sync failed: {exc}")
    _record(True, f"gist {gist_id}")

    user = _gh("api", "user", "--jq", ".login") if verbose else ""
    if verbose:
        raw = f"https://gist.githubusercontent.com/{user}/{gist_id}/raw/{GIST_FILENAME}"
        print(f"synced {len(blob['levels'])} days of aggregates")
        print(f"widget URL: {raw}")
    return gist_id
