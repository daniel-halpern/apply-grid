"""Push an aggregate snapshot to a secret gist for the phone widget to read.

Privacy is the whole design constraint here. A secret gist's raw URL is
unguessable but unauthenticated -- anyone holding the URL can read it -- so the
payload carries only counts and intensity levels. No company names, no roles,
no URLs, no notes ever leave the machine.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from . import config
from .model import State, bucket

GIST_FILENAME = "applygrid.json"
HISTORY_DAYS = 371          # 53 weeks, what the widget can show at most


def payload(state: State) -> dict:
    """Aggregates only. Read this function before trusting the sync."""
    start = state.today - timedelta(days=HISTORY_DAYS - 1)
    levels = "".join(
        str(bucket(state.points_on(start + timedelta(days=i)), state.target))
        for i in range(HISTORY_DAYS))
    funnel = state.funnel
    return {
        "v": 1,
        "start": start.isoformat(),
        "today": state.today.isoformat(),
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


def _gh(*args: str) -> str:
    proc = subprocess.run(("gh",) + args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gh failed")
    return proc.stdout.strip()


def sync(state: State, verbose: bool = True, quiet_fail: bool = False,
         init: bool = False) -> str | None:
    cfg = config.load()
    blob = payload(state)
    assert_no_pii(blob)

    gist_id = cfg.get("gist_id")
    if not gist_id and not init:
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
                cfg["gist_id"] = gist_id
                config.save(cfg)
                if verbose:
                    print(f"created secret gist {gist_id}")
            else:
                _gh("gist", "edit", gist_id, "--filename", GIST_FILENAME,
                    str(local))
        except RuntimeError as exc:
            if quiet_fail:
                return None
            raise SystemExit(f"gist sync failed: {exc}")

    user = _gh("api", "user", "--jq", ".login") if verbose else ""
    if verbose:
        raw = f"https://gist.githubusercontent.com/{user}/{gist_id}/raw/{GIST_FILENAME}"
        print(f"synced {len(blob['levels'])} days of aggregates")
        print(f"widget URL: {raw}")
    return gist_id
