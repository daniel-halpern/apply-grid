"""A window for editing every entry in the log.

Runs as its own process: rumps owns the main thread in the menu bar app, and Tk
needs a main thread of its own. Launch it with `ja edit`, or from the menu bar.

Tk rather than AppKit because it's in the standard library -- no Xcode, no new
dependency -- and a sortable table with a form beside it is all this needs.
"""

from __future__ import annotations

import json
import tkinter as tk
from datetime import date, datetime, time
from tkinter import messagebox, ttk

from . import background, config, events, model, publish, window

# Editable in the form; id and app_id are shown read-only because changing them
# would silently orphan an application's outcome events.
SOURCES = ("cold", "referral", "recruiter", "event", "inbound")
COLUMNS = (
    ("when", "When", 150),
    ("kind", "Kind", 175),
    ("company", "Company", 175),
    ("role", "Role", 175),
    ("pts", "Pts", 45),
)


class Row:
    """One log line, plus where it sits in the file."""

    def __init__(self, index: int, blob: dict):
        self.index = index
        self.blob = blob

    @property
    def ts(self) -> datetime:
        return events.parse_ts(self.blob["ts"])

    def points(self, weights: dict) -> int:
        return weights.get(self.blob.get("kind", ""), 0)


class Editor:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = config.load()
        self.rows: list[Row] = []
        self.sort_key = "when"
        self.sort_desc = True
        self.selected: Row | None = None
        self._loaded: dict[str, str] = {}

        root.title("Apply Grid — Entries")
        root.geometry("940x560")
        root.minsize(820, 420)

        self._build()
        self.reload()
        # A sync is ~800ms of network; inline it froze the window on each save.
        self.syncer = background.Syncer(root, on_status=self.say)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -- layout -------------------------------------------------------------
    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="Filter").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self.refresh_table())
        entry = ttk.Entry(bar, textvariable=self.filter_var, width=28)
        entry.pack(side="left", padx=(6, 12))
        self.count_label = ttk.Label(bar, text="")
        self.count_label.pack(side="left")
        ttk.Button(bar, text="Reload", command=self.reload).pack(side="right")
        ttk.Button(bar, text="Restore last removal",
                   command=self.restore).pack(side="right", padx=6)

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.tree = ttk.Treeview(
            left, columns=[c[0] for c in COLUMNS], show="headings",
            selectmode="browse")
        for key, title, width in COLUMNS:
            self.tree.heading(key, text=title,
                              command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width,
                             anchor="e" if key == "pts" else "w")
        bar_y = ttk.Scrollbar(left, orient="vertical",
                              command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar_y.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar_y.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        right = ttk.LabelFrame(body, text="Entry", padding=10)
        right.pack(side="left", fill="y", padx=(12, 0))
        self.fields: dict[str, tk.Variable] = {}

        def field(label: str, key: str, width: int = 26, values=None):
            ttk.Label(right, text=label).pack(anchor="w")
            var = tk.StringVar()
            if values is None:
                widget = ttk.Entry(right, textvariable=var, width=width)
            else:
                widget = ttk.Combobox(right, textvariable=var, width=width - 2,
                                      values=values, state="readonly")
            widget.pack(anchor="w", pady=(0, 7))
            self.fields[key] = var
            return widget

        when = ttk.Frame(right)
        ttk.Label(right, text="Date and time").pack(anchor="w")
        when.pack(anchor="w", pady=(0, 7))
        self.fields["date"] = tk.StringVar()
        self.fields["time"] = tk.StringVar()
        ttk.Entry(when, textvariable=self.fields["date"], width=12).pack(
            side="left")
        ttk.Entry(when, textvariable=self.fields["time"], width=7).pack(
            side="left", padx=(6, 0))

        # The dropdown shows the same human labels as the table, not the raw
        # keys stored in the log.
        self.kind_labels = {v: k for k, v in config.KIND_LABELS.items()}
        field("Kind", "kind", values=sorted(self.kind_labels))
        field("Company", "company")
        field("Role", "role")
        field("How you found it", "source", values=SOURCES)
        field("URL", "url")
        field("Notes", "notes")

        self.link_label = ttk.Label(right, text="", foreground="#666")
        self.link_label.pack(anchor="w", pady=(0, 8))

        buttons = ttk.Frame(right)
        buttons.pack(anchor="w", pady=(4, 0))
        self.save_button = ttk.Button(buttons, text="Save", command=self.save)
        self.save_button.pack(side="left")
        ttk.Button(buttons, text="Revert", command=self.on_select).pack(
            side="left", padx=6)
        ttk.Button(buttons, text="Delete", command=self.delete).pack(
            side="left")

        self.status = ttk.Label(outer, text="", foreground="#444")
        self.status.pack(anchor="w", pady=(8, 0))

    # -- data ---------------------------------------------------------------
    def reload(self) -> None:
        self.cfg = config.load()
        self.rows = [Row(i, json.loads(line))
                     for i, line in enumerate(events.read_lines())]
        state = model.build([r.blob for r in self.rows], self.cfg)
        self.apps = state.apps
        self.refresh_table()
        self.say(f"{len(self.rows)} entries loaded")

    def visible(self) -> list[Row]:
        needle = self.filter_var.get().strip().lower()
        rows = self.rows
        if needle:
            def matches(row: Row) -> bool:
                blob = row.blob
                haystack = " ".join(str(blob.get(k, "")) for k in
                                    ("company", "role", "kind", "source",
                                     "notes", "ts"))
                label = config.KIND_LABELS.get(blob.get("kind", ""), "")
                return needle in (haystack + " " + label).lower()
            rows = [r for r in rows if matches(r)]

        def key(row: Row):
            blob = row.blob
            if self.sort_key == "when":
                return row.ts
            if self.sort_key == "pts":
                return row.points(self.cfg["weights"])
            if self.sort_key == "kind":
                return config.KIND_LABELS.get(blob.get("kind", ""), "")
            return str(blob.get(self.sort_key, "")).lower()

        return sorted(rows, key=key, reverse=self.sort_desc)

    def refresh_table(self) -> None:
        keep = self.selected.index if self.selected else None
        self.tree.delete(*self.tree.get_children())
        weights = self.cfg["weights"]
        for row in self.visible():
            blob = row.blob
            company = blob.get("company", "")
            if not company and blob.get("app_id") in self.apps:
                company = self.apps[blob["app_id"]].company
            pts = row.points(weights)
            self.tree.insert(
                "", "end", iid=str(row.index),
                values=(row.ts.strftime("%d %b %Y  %-I:%M%p").lower(),
                        config.KIND_LABELS.get(blob.get("kind", ""),
                                               blob.get("kind", "?")),
                        company, blob.get("role", ""),
                        f"+{pts}" if pts else ""))
        shown = len(self.tree.get_children())
        self.count_label.configure(
            text=f"{shown} of {len(self.rows)} shown"
            if shown != len(self.rows) else f"{shown} entries")
        if keep is not None and self.tree.exists(str(keep)):
            self.tree.selection_set(str(keep))

    def sort_by(self, key: str) -> None:
        if self.sort_key == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key, self.sort_desc = key, key in ("when", "pts")
        self.refresh_table()

    # -- form ---------------------------------------------------------------
    def on_select(self, _event=None) -> None:
        picked = self.tree.selection()
        if not picked:
            return
        index = int(picked[0])
        self.selected = next((r for r in self.rows if r.index == index), None)
        if self.selected is None:
            return
        blob = self.selected.blob
        stamp = self.selected.ts
        self.fields["date"].set(stamp.strftime("%Y-%m-%d"))
        self.fields["time"].set(stamp.strftime("%H:%M"))
        self.fields["kind"].set(
            config.KIND_LABELS.get(blob.get("kind", ""), blob.get("kind", "")))
        for key in ("company", "role", "source", "url", "notes"):
            self.fields[key].set(str(blob.get(key, "")))
        bits = []
        if blob.get("id"):
            bits.append(f"application id {blob['id']}")
        if blob.get("app_id"):
            app = self.apps.get(blob["app_id"])
            who = f" ({app.company})" if app else ""
            bits.append(f"attached to {blob['app_id']}{who}")
        self.link_label.configure(
            text="  ·  ".join(bits) or "standalone entry")
        self._loaded = self.form_values()

    def form_values(self) -> dict[str, str]:
        return {k: v.get() for k, v in self.fields.items()}

    def has_unsaved_edits(self) -> bool:
        """Text typed into the form but never written to the log."""
        return bool(self._loaded) and self.form_values() != self._loaded

    def on_close(self) -> None:
        """Typing in a field is not on disk until Save, so ask before losing it."""
        if self.has_unsaved_edits():
            changed = [k for k, v in self.form_values().items()
                       if self._loaded.get(k) != v]
            if not messagebox.askyesno(
                    "Discard unsaved changes?",
                    "These fields were edited but not saved:\n\n  "
                    + ", ".join(sorted(changed))
                    + "\n\nClose anyway?", parent=self.root):
                return
        self.root.destroy()

    def collect(self) -> dict | None:
        """Read the form back into an event, or complain and return None."""
        assert self.selected is not None
        blob = dict(self.selected.blob)
        raw_date = self.fields["date"].get().strip()
        raw_time = self.fields["time"].get().strip() or "12:00"
        try:
            day = date.fromisoformat(raw_date)
        except ValueError:
            self.fail(f"Date must be YYYY-MM-DD, got {raw_date!r}")
            return None
        try:
            hour, _, minute = raw_time.partition(":")
            moment = time(int(hour), int(minute or 0))
        except ValueError:
            self.fail(f"Time must be HH:MM, got {raw_time!r}")
            return None
        if day > date.today():
            self.fail("That date is in the future.")
            return None

        chosen = self.fields["kind"].get().strip()
        kind = self.kind_labels.get(chosen, chosen)
        if kind not in config.KIND_LABELS:
            self.fail(f"Unknown kind {chosen!r}")
            return None
        if kind in config.APPLICATION_KINDS and not \
                self.fields["company"].get().strip():
            self.fail("An application needs a company name.")
            return None

        blob["ts"] = datetime.combine(day, moment).astimezone() \
            .replace(microsecond=0).isoformat()
        blob["kind"] = kind
        for key in ("company", "role", "source", "url", "notes"):
            value = self.fields[key].get().strip()
            if value or key in blob:
                blob[key] = value
        return blob

    # -- actions ------------------------------------------------------------
    def save(self) -> None:
        if self.selected is None:
            self.fail("Pick an entry first.")
            return
        blob = self.collect()
        if blob is None:
            return
        if blob == self.selected.blob:
            self.say("No changes to save.")
            return
        index = self.selected.index
        events.replace_index(index, blob)
        self._loaded = self.form_values()
        self.after_write("Saved.", keep_index=index)

    def delete(self) -> None:
        if self.selected is None:
            self.fail("Pick an entry first.")
            return
        summary = events.describe(self.selected.blob)
        if not messagebox.askyesno(
                "Remove this entry?",
                f"{summary}\n\nIt goes to removed.jsonl and can be put back "
                f"with “Restore last removal”.", parent=self.root):
            return
        events.remove_indices({self.selected.index})
        self.selected = None
        self.after_write("Removed.")

    def restore(self) -> None:
        back = events.restore_last()
        if not back:
            self.say("Nothing to restore.")
            return
        self.after_write(f"Restored {len(back)} entr"
                         f"{'y' if len(back) == 1 else 'ies'}.")

    def after_write(self, message: str, keep_index: int | None = None) -> None:
        """Reload, then push to the phone.

        Holding the selection matters: without it, saving one field drops the
        row and a second correction needs another click.
        """
        self.selected = None
        self.reload()
        if keep_index is not None and self.tree.exists(str(keep_index)):
            self.tree.selection_set(str(keep_index))
            self.on_select()
        self.say(message)
        self.syncer.request()          # debounced, reports back when it lands

    def say(self, message: str) -> None:
        self.status.configure(text=message, foreground="#444")

    def fail(self, message: str) -> None:
        self.status.configure(text=message, foreground="#b00")


def main() -> None:
    root = tk.Tk()
    Editor(root)
    window.bring_to_front(root)
    root.mainloop()


if __name__ == "__main__":
    main()
