"""Configuration loading.

Config lives in config.json rather than TOML because this targets the system
Python 3.10, which predates tomllib.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "daily_target": 3,
    "weekly_target_multiplier": 4,
    "stale_after_days": 10,
    "give_up_after_days": 45,
    "weights": {
        "application_tailored": 3,
        "application_quick": 1,
        "referral_ask": 2,
        "cold_outreach": 2,
        "follow_up": 1,
        "interview": 5,
        "resume_work": 2,
        "prep": 1,
    },
    "gist_id": None,
}

# Effort events carry points and create or touch an application.
# These two create a new application; the rest attach to an existing one
# (or stand alone, for generic effort like resume work).
APPLICATION_KINDS = ("application_tailored", "application_quick")

# Outcome events. Worth zero points -- you don't get credit for what the
# other side did -- but they drive the funnel and clear the stale list.
STAGE_ORDER = ("applied", "screen", "technical", "onsite", "offer")
STAGE_KINDS = {
    "response_screen": "screen",
    "response_technical": "technical",
    "response_onsite": "onsite",
    "offer": "offer",
}
TERMINAL_KINDS = ("rejected", "withdrawn")

# Human labels, used by every renderer so the surfaces stay consistent.
KIND_LABELS = {
    "application_tailored": "Tailored application",
    "application_quick": "Quick application",
    "referral_ask": "Referral ask",
    "cold_outreach": "Cold outreach",
    "follow_up": "Follow-up",
    "interview": "Interview",
    "resume_work": "Resume / portfolio work",
    "prep": "Interview prep",
    "response_screen": "Got a screen",
    "response_technical": "Got a technical",
    "response_onsite": "Got an onsite",
    "offer": "Offer",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
}


def data_path() -> Path:
    """Event log location. APPLYGRID_DATA overrides, for tests and fixtures."""
    override = os.environ.get("APPLYGRID_DATA")
    if override:
        return Path(override).expanduser()
    return REPO_ROOT / "data" / "events.jsonl"


def config_path() -> Path:
    override = os.environ.get("APPLYGRID_CONFIG")
    if override:
        return Path(override).expanduser()
    return REPO_ROOT / "config.json"


def load() -> dict:
    """Load config, falling back to defaults for anything missing."""
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    path = config_path()
    if path.exists():
        try:
            user = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError as exc:
            raise SystemExit(f"config.json is not valid JSON: {exc}")
        weights = user.pop("weights", None) or {}
        cfg.update(user)
        cfg["weights"].update(weights)
    if cfg["daily_target"] <= 0:
        raise SystemExit("daily_target must be greater than 0")
    return cfg


def save(cfg: dict) -> None:
    config_path().write_text(json.dumps(cfg, indent=2) + "\n")
