"""Append-only event log.

One JSON object per line, never rewritten. Everything else in this project is
a pure fold over this file, so the log is the only thing that needs backing up
and the only thing a future email-ingester would have to write to.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from . import config


def now_iso() -> str:
    """Local time with an explicit offset, so grids stay correct across DST."""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def read(path: Path | None = None) -> list[dict]:
    """Read every event, oldest first. Skips blank lines; reports bad ones."""
    path = path or config.data_path()
    if not path.exists():
        return []
    out = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{lineno} is not valid JSON: {exc}")
    out.sort(key=lambda e: e["ts"])
    return out


def append(event: dict, path: Path | None = None) -> dict:
    """Append one event. Creates the log and its parent directory if needed."""
    path = path or config.data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False)
    # Open in append mode so concurrent writers (CLI + menu bar) can't clobber
    # each other; a single short line is written atomically in practice.
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return event


def new_id(existing: list[dict]) -> str:
    """Short, human-typeable id that doesn't collide with anything on disk."""
    taken = {e["id"] for e in existing if e.get("id")}
    while True:
        candidate = secrets.token_hex(2)
        if candidate not in taken:
            return candidate
