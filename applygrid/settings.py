"""Settings window: switch surfaces off, pin the colour ramp, change targets.

Preferences are written to config.local.json, so they stay out of the repo and
never conflict with the committed defaults in config.json.

Changes apply the moment you make them. The first version had a Save button
below the fold in a fixed-height window, so it was unreachable and nothing
appeared to work.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import background, config, window

SCHEMES = (
    ("auto", "Follow the host (dark terminal, phone appearance)"),
    ("light", "Light — darker green means more"),
    ("dark", "Dark — brighter green means more"),
)

ANCHORS = (
    ("today", "Today in the bottom-right corner, no gaps"),
    ("sunday", "GitHub's layout (leaves a notch for the rest of this week)"),
)

SURFACES = (
    ("desktop_widget", "Desktop widget",
     "The grid on your desktop, drawn by Übersicht"),
    ("terminal", "Terminal grid",
     "Printed when you open a new shell"),
    ("phone_sync", "Phone sync",
     "Pushes aggregates to the secret gist your iPhone widget reads"),
)

NUMBERS = (
    ("daily_target", "Points for a full day", 1, 50),
    ("weekly_target_multiplier", "Good days per week", 1, 7),
    ("stale_after_days", "Chase a quiet application after (days)", 1, 120),
    ("give_up_after_days", "Treat it as cold after (days)", 2, 365),
)


class Settings:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = config.load()
        self.vars: dict[str, tk.Variable] = {}
        self.live = False          # suppress writes while building

        root.title("Apply Grid — Settings")
        window.center(root, 580, 640)
        root.minsize(480, 360)

        self._build()
        # A sync is ~800ms of network; inline it froze the window on each click.
        self.syncer = background.Syncer(root, on_status=self.say)
        self.live = True
        root.protocol("WM_DELETE_WINDOW", root.destroy)

    # -- layout -------------------------------------------------------------
    def _build(self) -> None:
        # Footer first, packed to the bottom, so it can never be pushed off
        # screen by the content above it.
        footer = ttk.Frame(self.root, padding=(14, 8))
        footer.pack(side="bottom", fill="x")
        ttk.Button(footer, text="Close",
                   command=self.root.destroy).pack(side="right")
        self.status = ttk.Label(footer, text="Changes apply immediately.",
                                foreground="#666")
        self.status.pack(side="left")
        ttk.Separator(self.root, orient="horizontal").pack(
            side="bottom", fill="x")

        # Scrolling content.
        holder = ttk.Frame(self.root)
        holder.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(holder, borderwidth=0, highlightthickness=0)
        scroll = ttk.Scrollbar(holder, orient="vertical",
                               command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = ttk.Frame(canvas, padding=16)
        slot = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(slot, width=e.width))
        # Trackpad and wheel scrolling.
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1 * int(e.delta),
                                                      "units"))
        self._fill(body)

    def _fill(self, body: ttk.Frame) -> None:
        surfaces = ttk.LabelFrame(body, text="Surfaces", padding=12)
        surfaces.pack(fill="x")
        for key, label, hint in SURFACES:
            var = tk.BooleanVar(value=config.surface_enabled(key, self.cfg))
            self.vars[f"surfaces.{key}"] = var
            ttk.Checkbutton(surfaces, text=label, variable=var,
                            command=self.apply).pack(anchor="w")
            ttk.Label(surfaces, text=hint, foreground="#777").pack(
                anchor="w", padx=(22, 0), pady=(0, 6))
        ttk.Label(surfaces,
                  text="The menu bar can't be switched off here — quit it "
                       "from its own menu.",
                  foreground="#777").pack(anchor="w")

        colours = ttk.LabelFrame(body, text="Colour", padding=12)
        colours.pack(fill="x", pady=(12, 0))
        scheme = tk.StringVar(value=self.cfg.get("color_scheme", "auto"))
        self.vars["color_scheme"] = scheme
        for value, label in SCHEMES:
            ttk.Radiobutton(colours, text=label, value=value, variable=scheme,
                            command=self.apply).pack(anchor="w")
        ttk.Label(colours,
                  text="Your phone follows its own appearance, so in light "
                       "mode darker\ngreen already means more. Pinning "
                       "“light” also applies to the terminal,\nwhere "
                       "dark greens on a dark background look washed out.",
                  foreground="#777", justify="left").pack(anchor="w",
                                                          pady=(6, 0))

        layout = ttk.LabelFrame(body, text="Grid layout", padding=12)
        layout.pack(fill="x", pady=(12, 0))
        anchor = tk.StringVar(value=self.cfg.get("week_anchor", "today"))
        self.vars["week_anchor"] = anchor
        for value, label in ANCHORS:
            ttk.Radiobutton(layout, text=label, value=value, variable=anchor,
                            command=self.apply).pack(anchor="w")

        nudges = ttk.LabelFrame(body, text="Daily nudge", padding=12)
        nudges.pack(fill="x", pady=(12, 0))
        cfg_nudges = self.cfg.get("nudges", {})
        enabled = tk.BooleanVar(value=bool(cfg_nudges.get("enabled", True)))
        self.vars["nudges.enabled"] = enabled
        ttk.Checkbutton(nudges, text="Notify me when today is still short",
                        variable=enabled, command=self.apply).pack(anchor="w")
        ttk.Label(nudges,
                  text="Only fires when it can still change the outcome, so a "
                       "day you've\nalready hit target is silent. It names "
                       "what's actually due rather\nthan repeating itself, and "
                       "goes quiet for a week if ignored three\ntimes running.",
                  foreground="#777", justify="left").pack(anchor="w",
                                                          pady=(2, 8))
        for key, label, low, high in (
                ("window_start_hour", "Not before (hour, 24h)", 0, 23),
                ("window_end_hour", "Not after (hour, 24h)", 1, 24),
                ("max_per_week", "At most per week", 1, 14)):
            row = ttk.Frame(nudges)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label).pack(side="left")
            var = tk.IntVar(value=int(cfg_nudges.get(key, low)))
            self.vars[f"nudges.{key}"] = var
            spin = ttk.Spinbox(row, from_=low, to=high, textvariable=var,
                               width=5, command=self.apply)
            spin.pack(side="right")
            spin.bind("<Return>", lambda _e: self.apply())
            spin.bind("<FocusOut>", lambda _e: self.apply())
        weekends = tk.BooleanVar(
            value=bool(cfg_nudges.get("skip_weekends", False)))
        self.vars["nudges.skip_weekends"] = weekends
        ttk.Checkbutton(nudges, text="Stay quiet at weekends",
                        variable=weekends, command=self.apply).pack(
            anchor="w", pady=(4, 0))
        ttk.Label(nudges, text="When there's nothing specific to report, say:"
                  ).pack(anchor="w", pady=(8, 0))
        fallback = tk.StringVar(
            value=str(cfg_nudges.get("fallback_message",
                                     "Anything worth applying to today?")))
        self.vars["nudges.fallback_message"] = fallback
        entry = ttk.Entry(nudges, textvariable=fallback, width=44)
        entry.pack(anchor="w", pady=(2, 0))
        entry.bind("<Return>", lambda _e: self.apply())
        entry.bind("<FocusOut>", lambda _e: self.apply())
        ttk.Button(nudges, text="Send one now to see how it looks",
                   command=self.test_nudge).pack(anchor="w", pady=(8, 0))

        goals = ttk.LabelFrame(body, text="Targets", padding=12)
        goals.pack(fill="x", pady=(12, 0))
        for key, label, low, high in NUMBERS:
            row = ttk.Frame(goals)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label).pack(side="left")
            var = tk.IntVar(value=int(self.cfg.get(key, low)))
            self.vars[key] = var
            spin = ttk.Spinbox(row, from_=low, to=high, textvariable=var,
                               width=5, command=self.apply)
            spin.pack(side="right")
            # Typed values commit on Enter or when focus leaves the field.
            spin.bind("<Return>", lambda _e: self.apply())
            spin.bind("<FocusOut>", lambda _e: self.apply())

    # -- persistence --------------------------------------------------------
    def collect(self) -> dict | None:
        values: dict = {"surfaces": {}}
        for name, var in self.vars.items():
            try:
                value = var.get()
            except tk.TclError:
                self.fail("That needs to be a whole number.")
                return None
            if name.startswith("surfaces."):
                values["surfaces"][name.split(".", 1)[1]] = bool(value)
            elif name.startswith("nudges."):
                key = name.split(".", 1)[1]
                values.setdefault("nudges", {})[key] = (
                    bool(value) if isinstance(value, bool) else value)
            else:
                values[name] = value
        if int(values["daily_target"]) < 1:
            self.fail("A full day needs at least 1 point.")
            return None
        nudges = values.get("nudges", {})
        if nudges and int(nudges.get("window_end_hour", 24)) <= \
                int(nudges.get("window_start_hour", 0)):
            self.fail("The nudge window needs an end later than its start.")
            return None
        if int(values["give_up_after_days"]) <= int(values["stale_after_days"]):
            self.fail("“Cold” must be longer than “chase”, "
                      "or nothing would reach the follow-up list.")
            return None
        return values

    def apply(self) -> None:
        if not self.live:
            return
        values = self.collect()
        if values is None:
            return
        config.update_local(values)
        self.cfg = config.load()
        self.refresh_surfaces(values)

    def refresh_surfaces(self, values: dict) -> None:
        """Make the change visible now rather than at the next refresh."""
        notes = []
        # The startup grid is cached against the log's mtime, so a settings
        # change would otherwise not show until the next entry.
        cache = config.REPO_ROOT / ".cache"
        if cache.exists():
            for stale in cache.glob("startup-*.txt"):
                stale.unlink(missing_ok=True)
            notes.append("terminal")
        widget = (config.Path.home() / "Library" / "Application Support"
                  / "Übersicht" / "widgets" / "apply-grid.widget"
                  / "index.jsx")
        if widget.exists():
            widget.touch()          # nudges Ubersicht into re-rendering
            notes.append("desktop")
        if values["surfaces"].get("phone_sync"):
            self.syncer.request()      # debounced, reports back when it lands
        suffix = f" — refreshed {', '.join(notes)}" if notes else ""
        self.say(f"Saved.{suffix}")

    def test_nudge(self) -> None:
        """Show the message that would fire right now, ignoring the schedule."""
        from . import events, model, nudge, notify
        state = model.build(events.read(), self.cfg)
        preview = nudge.compose(state)
        if notify.send(preview.title, preview.message, preview.subtitle):
            self.say(f"Sent: {preview.title}")
        else:
            self.fail("Could not send a notification.")

    def say(self, message: str) -> None:
        self.status.configure(text=message, foreground="#444")

    def fail(self, message: str) -> None:
        self.status.configure(text=message, foreground="#b00")


def main() -> None:
    root = tk.Tk()
    Settings(root)
    window.bring_to_front(root)
    root.mainloop()


if __name__ == "__main__":
    main()
