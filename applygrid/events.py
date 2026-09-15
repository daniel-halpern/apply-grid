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


TRASH_NAME = "removed.jsonl"


def trash_path(path: Path | None = None) -> Path:
    """Where removed events go. Nothing is ever truly destroyed."""
    path = path or config.data_path()
    return path.parent / TRASH_NAME


def read_lines(path: Path | None = None) -> list[str]:
    """Raw lines in file order.

    read() sorts by timestamp; removal must work on file order so that "undo
    the last thing I did" means the last line appended, not the latest date.
    """
    path = path or config.data_path()
    if not path.exists():
        return []
    return [l for l in path.read_text().splitlines() if l.strip()]


def _rewrite(lines: list[str], path: Path) -> None:
    """Replace the log atomically, so an interrupted write can't truncate it."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(l + "\n" for l in lines), encoding="utf-8")
    os.replace(tmp, path)


def remove_indices(indices: set[int], path: Path | None = None) -> list[dict]:
    """Drop lines by file index, keeping a copy in removed.jsonl.

    The log is append-only in normal use, but a typo you can't take back is
    worse than a rewrite. Removed events are appended to a sibling trash file
    with a batch stamp, so `restore` can put them back.
    """
    path = path or config.data_path()
    lines = read_lines(path)
    keep, gone = [], []
    for i, line in enumerate(lines):
        (gone if i in indices else keep).append(line)
    if not gone:
        return []
    # A distinct batch id per removal. now_iso() is second-resolution, so two
    # removals in the same second collided into one batch and `restore` brought
    # back both.
    stamp = (datetime.now().astimezone().isoformat() + "#"
             + secrets.token_hex(3))
    trash = trash_path(path)
    trash.parent.mkdir(parents=True, exist_ok=True)
    with trash.open("a", encoding="utf-8") as fh:
        for line in gone:
            blob = json.loads(line)
            blob["_removed_at"] = stamp
            fh.write(json.dumps(blob, ensure_ascii=False) + "\n")
    _rewrite(keep, path)
    return [json.loads(l) for l in gone]


def replace_index(index: int, event: dict,
                  path: Path | None = None) -> dict | None:
    """Rewrite one line in place, archiving the previous version.

    The old row goes to removed.jsonl tagged `_edited_at` rather than
    `_removed_at`, so it forms an audit trail without restore_last treating an
    edit as a removal batch.
    """
    path = path or config.data_path()
    lines = read_lines(path)
    if not 0 <= index < len(lines):
        return None
    previous = json.loads(lines[index])
    trash = trash_path(path)
    trash.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat()
    with trash.open("a", encoding="utf-8") as fh:
        archived = dict(previous)
        archived["_edited_at"] = stamp
        fh.write(json.dumps(archived, ensure_ascii=False) + "\n")
    lines[index] = json.dumps(event, ensure_ascii=False)
    _rewrite(lines, path)
    return previous


def restore_last(path: Path | None = None) -> list[dict]:
    """Put the most recent removal batch back."""
    path = path or config.data_path()
    trash = trash_path(path)
    if not trash.exists():
        return []
    rows = [json.loads(l) for l in trash.read_text().splitlines() if l.strip()]
    # Only removals are restorable. Edits are archived here too, and a plain
    # max() over a missing key yields "" -- which matched every edit row and
    # re-appended them as if they had been deleted.
    removals = [i for i, r in enumerate(rows) if r.get("_removed_at")]
    if not removals:
        return []
    latest = max(rows[i]["_removed_at"] for i in removals)
    batch = [i for i in removals if rows[i]["_removed_at"] == latest]
    back = []
    for i in batch:
        row = dict(rows[i])
        row.pop("_removed_at", None)
        append(row, path)
        back.append(row)
    keep = [r for i, r in enumerate(rows) if i not in set(batch)]
    trash.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                             for r in keep), encoding="utf-8")
    return back


def describe(event: dict, company: str = "") -> str:
    """One-line human summary, shared by undo prompts and the menu bar."""
    label = config.KIND_LABELS.get(event.get("kind", ""), event.get("kind", "?"))
    who = event.get("company") or company
    role = event.get("role", "")
    when = parse_ts(event["ts"]).strftime("%-d %b %-I:%M%p").lower()
    if who and role:
        return f"{label} \u2014 {who} / {role}  ({when})"
    if who:
        return f"{label} \u2014 {who}  ({when})"
    return f"{label}  ({when})"


def new_id(existing: list[dict]) -> str:
    """Short, human-typeable id that doesn't collide with anything on disk."""
    taken = {e["id"] for e in existing if e.get("id")}
    while True:
        candidate = secrets.token_hex(2)
        if candidate not in taken:
            return candidate
