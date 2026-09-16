"""macOS menu bar app: the always-visible surface and the only logging path.

Deliberately thin -- every number comes from model.State and every write goes
through events.append, so this file holds no logic the other surfaces don't
already share.
"""

from __future__ import annotations

import json
import threading

try:
    import rumps
except ImportError:  # pragma: no cover
    raise SystemExit(
        "the menu bar app needs rumps:\n"
        "  cd <repo> && python3 -m venv .venv && "
        ".venv/bin/pip install rumps")

from . import config, events, model, nudge, publish, render_menubar

REFRESH_SECONDS = 60

EFFORT_CHOICES = [
    ("prep", "Interview prep"),
    ("resume_work", "Resume / portfolio work"),
    ("referral_ask", "Referral ask"),
    ("cold_outreach", "Cold outreach"),
    ("interview", "Interview"),
]


class ApplyGrid(rumps.App):
    def __init__(self):
        super().__init__("apply-grid", title="…", quit_button="Quit")
        self.state = self._load()
        self._build_menu()
        rumps.Timer(self._tick, REFRESH_SECONDS).start()

    # -- data ---------------------------------------------------------------
    def _load(self) -> model.State:
        return model.build(events.read(), config.load())

    def _refresh(self) -> None:
        self.state = self._load()
        self.title = render_menubar.title(self.state)
        self._build_menu()

    def _tick(self, _timer) -> None:
        self._refresh()
        self._maybe_nudge()

    def _maybe_nudge(self) -> None:
        """Checked once a minute; nudge.evaluate decides if anything fires.

        Threaded because delivery shells out to osascript, and the menu must
        not stall behind it.
        """
        def run():
            try:
                nudge.maybe_send(self.state)
            except Exception:  # noqa: BLE001 - a nudge must never break the app
                pass
        threading.Thread(target=run, daemon=True).start()

    def _sync_async(self) -> None:
        """Push to the phone without making the click feel slow."""
        def run():
            try:
                publish.sync(self.state, verbose=False, quiet_fail=True)
            except Exception as exc:  # noqa: BLE001
                publish._record(False, f"{type(exc).__name__}: {exc}")
        threading.Thread(target=run, daemon=True).start()

    # -- menu ---------------------------------------------------------------
    def _build_menu(self) -> None:
        self.title = render_menubar.title(self.state)
        items: list = []
        for line in render_menubar.header_lines(self.state):
            items.append(rumps.MenuItem(line) if line
                         else rumps.separator)
        status = publish.last_status()
        if status and not status.get("ok") and not status.get("skipped"):
            detail = str(status.get("detail", "?"))[:46]
            items.append(rumps.MenuItem(f"⚠ phone sync failing — {detail}"))
        items.append(rumps.separator)

        items.append(rumps.MenuItem("Log tailored application…",
                                    callback=self.log_tailored))
        items.append(rumps.MenuItem("Log quick application…",
                                    callback=self.log_quick))

        effort = rumps.MenuItem("Log effort")
        for kind, label in EFFORT_CHOICES:
            effort.add(rumps.MenuItem(
                f"{label}  +{self.state.cfg['weights'].get(kind, 0)}",
                callback=self._effort_cb(kind)))
        items.append(effort)

        stale = self.state.stale()
        follow = rumps.MenuItem(f"Follow up on ({len(stale)})" if stale
                                else "Follow up on")
        if stale:
            for app in stale[:12]:
                quiet = app.days_since_last_event(self.state.today)
                follow.add(rumps.MenuItem(
                    f"{app.company} — {quiet}d quiet",
                    callback=self._followup_cb(app.id)))
        else:
            follow.add(rumps.MenuItem("nothing owed right now"))
        items.append(follow)

        items.append(rumps.MenuItem("Record an outcome…",
                                    callback=self.record_outcome))
        items.append(rumps.MenuItem("Edit entries…",
                                    callback=self.open_editor))

        # The question a green square makes you ask. Desktop and phone widgets
        # can't answer it -- neither is clickable -- so it lives here.
        days = model.active_days(self.state, 14)
        history = rumps.MenuItem("What did I do on…")
        if days:
            for day, pts in days:
                label = f"{day.strftime('%a %-d %b')}   {pts} pts"
                history.add(rumps.MenuItem(label, callback=self._day_cb(day)))
        else:
            history.add(rumps.MenuItem("nothing logged yet"))
        items.append(history)
        items.append(rumps.separator)

        # An escape hatch for mistakes, right next to the thing that makes
        # them. Naming what will be removed matters more than the verb.
        lines = events.read_lines()
        if lines:
            last = json.loads(lines[-1])
            company = ""
            if last.get("app_id"):
                app = self.state.apps.get(last["app_id"])
                company = app.company if app else ""
            items.append(rumps.MenuItem(
                f"Undo: {events.describe(last, company)}",
                callback=self.undo_last))
        else:
            items.append(rumps.MenuItem("Undo"))

        recent = sorted(self.state.apps.values(),
                        key=lambda a: a.applied_on, reverse=True)
        remove = rumps.MenuItem("Remove an application")
        if recent:
            for app in recent[:15]:
                label = f"{app.company}"
                if app.role:
                    label += f" / {app.role}"
                remove.add(rumps.MenuItem(label,
                                          callback=self._remove_cb(app.id)))
        else:
            remove.add(rumps.MenuItem("nothing logged yet"))
        items.append(remove)

        if events.trash_path().exists():
            items.append(rumps.MenuItem("Restore last removal",
                                        callback=self.restore_last))

        items.append(rumps.separator)
        items.append(rumps.MenuItem("Settings…",
                                    callback=self.open_settings))
        items.append(rumps.separator)
        items.append(rumps.MenuItem("Sync to phone now",
                                    callback=self.sync_now))
        items.append(rumps.MenuItem("Refresh", callback=lambda _: self._refresh()))
        self.menu.clear()
        self.menu = items

    # -- actions ------------------------------------------------------------
    def _ask(self, title: str, message: str, placeholder: str = ""):
        win = rumps.Window(message=message, title=title,
                           default_text=placeholder, ok="Log",
                           cancel="Cancel", dimensions=(280, 22))
        response = win.run()
        return response.text.strip() if response.clicked else None

    def _log_application(self, kind: str) -> None:
        raw = self._ask(
            "Log an application",
            "Company / Role\n\nAdd  @referral,  @recruiter  or  @event "
            "to mark how you found it.",
            "")
        if not raw:
            return
        source = "cold"
        for tag in ("referral", "recruiter", "event"):
            if f"@{tag}" in raw.lower():
                source = tag
                raw = raw.replace(f"@{tag}", "").replace(f"@{tag.title()}", "")
        company, _, role = raw.partition("/")
        company = company.strip()
        if not company:
            rumps.alert("Nothing logged", "A company name is required.")
            return
        existing = events.read()
        events.append({
            "id": events.new_id(existing),
            "ts": events.now_iso(),
            "kind": kind,
            "company": company,
            "role": role.strip(),
            "source": source,
            "url": "",
            "notes": "",
        })
        self._refresh()
        self._sync_async()
        rumps.notification(
            "Logged", f"{company} — +{self.state.cfg['weights'][kind]} pts",
            f"{self.state.points_on(self.state.today)}/{self.state.target} "
            f"today · {self.state.streak_days}d streak")

    def log_tailored(self, _) -> None:
        self._log_application("application_tailored")

    def log_quick(self, _) -> None:
        self._log_application("application_quick")

    def _effort_cb(self, kind: str):
        def cb(_):
            events.append({"ts": events.now_iso(), "kind": kind})
            self._refresh()
            self._sync_async()
        return cb

    def _followup_cb(self, app_id: str):
        def cb(_):
            events.append({"ts": events.now_iso(), "kind": "follow_up",
                           "app_id": app_id})
            self._refresh()
            self._sync_async()
        return cb

    def record_outcome(self, _) -> None:
        raw = self._ask(
            "Record an outcome",
            "company  outcome\n\ne.g.  stripe screen   ·   ramp offer"
            "   ·   figma rejected",
            "")
        if not raw:
            return
        from .cli import resolve_kind
        parts = raw.split()
        if len(parts) < 2:
            rumps.alert("Nothing logged", "Give a company and an outcome.")
            return
        ref, kind_raw = " ".join(parts[:-1]), parts[-1]
        try:
            kind = resolve_kind(kind_raw)
        except SystemExit as exc:
            rumps.alert("Unknown outcome", str(exc))
            return
        matches = [a for a in self.state.apps.values()
                   if ref.lower() in a.company.lower() or a.id == ref]
        live = [a for a in matches if a.is_live] or matches
        if len(live) != 1:
            rumps.alert("Which one?", f"{ref!r} matched {len(live)} applications.")
            return
        events.append({"ts": events.now_iso(), "kind": kind,
                       "app_id": live[0].id})
        self._refresh()
        self._sync_async()

    def undo_last(self, _) -> None:
        lines = events.read_lines()
        if not lines:
            return
        last = json.loads(lines[-1])
        company = ""
        if last.get("app_id"):
            app = self.state.apps.get(last["app_id"])
            company = app.company if app else ""
        if rumps.alert("Remove this?", events.describe(last, company),
                       ok="Remove", cancel="Keep") != 1:
            return
        events.remove_indices({len(lines) - 1})
        self._refresh()
        self._sync_async()

    def _remove_cb(self, app_id: str):
        def cb(_):
            app = self.state.apps.get(app_id)
            if app is None:
                return
            lines = events.read_lines()
            indices = {i for i, line in enumerate(lines)
                       if json.loads(line).get("id") == app_id
                       or json.loads(line).get("app_id") == app_id}
            plural = "s" if len(indices) != 1 else ""
            if rumps.alert(
                    f"Remove {app.company}?",
                    f"This removes the application and its {len(indices)} "
                    f"event{plural}. You can put it back with "
                    f"“Restore last removal”.",
                    ok="Remove", cancel="Keep") != 1:
                return
            events.remove_indices(indices)
            self._refresh()
            self._sync_async()
        return cb

    def restore_last(self, _) -> None:
        back = events.restore_last()
        self._refresh()
        self._sync_async()
        if back:
            rumps.notification("Restored", f"{len(back)} event(s) put back", "")

    def _day_cb(self, day):
        def cb(_):
            rows = model.events_on(events.read(), day, self.state.apps)
            lines = []
            for row in rows:
                label = config.KIND_LABELS.get(row["kind"], row["kind"])
                who = row.get("company", "")
                role = row.get("role", "")
                name = f"{who}{' / ' + role if role else ''}" if who else ""
                lines.append(f"{label}{'  —  ' + name if name else ''}")
            rumps.alert(
                day.strftime("%A %-d %B"),
                "\n".join(lines) or "nothing logged",
                ok="Close")
        return cb

    def _open_window(self, module: str, label: str) -> None:
        """Launch a Tk window as its own process.

        rumps owns this thread's run loop and Tk needs a main thread of its
        own, so a window cannot be opened in-process. The window raises itself
        to the front on start, since the menu bar agent isn't the active app.
        """
        import os
        import subprocess
        import sys
        root = str(config.REPO_ROOT)
        env = dict(os.environ, PYTHONPATH=root)
        try:
            subprocess.Popen([sys.executable, "-m", module],
                             cwd=root, env=env,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as exc:
            rumps.alert(f"Could not open {label}", str(exc))

    def open_editor(self, _) -> None:
        self._open_window("applygrid.editor", "the editor")

    def open_settings(self, _) -> None:
        self._open_window("applygrid.settings", "settings")

    def sync_now(self, _) -> None:
        """Explicit sync. Threaded, so the menu doesn't hang for ~800ms."""
        def run():
            try:
                gist = publish.sync(self.state, verbose=False)
            except SystemExit as exc:
                rumps.notification("Sync failed", str(exc), "")
                return
            if gist:
                rumps.notification("Synced", "Phone widget updated", "")
            else:
                status = publish.last_status()
                rumps.notification(
                    "Nothing sent", status.get("detail", "") if status else "",
                    "")
        threading.Thread(target=run, daemon=True).start()


def main() -> None:
    ApplyGrid().run()


if __name__ == "__main__":
    main()
