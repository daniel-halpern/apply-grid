"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time

from . import config, events, model, palette, render_ansi

# Short names for the things you'd actually type.
ALIASES = {
    "tailored": "application_tailored",
    "quick": "application_quick",
    "referral": "referral_ask",
    "outreach": "cold_outreach",
    "cold": "cold_outreach",
    "followup": "follow_up",
    "follow-up": "follow_up",
    "interview": "interview",
    "resume": "resume_work",
    "portfolio": "resume_work",
    "prep": "prep",
    "screen": "response_screen",
    "technical": "response_technical",
    "tech": "response_technical",
    "onsite": "response_onsite",
    "final": "response_onsite",
    "offer": "offer",
    "reject": "rejected",
    "rejected": "rejected",
    "ghosted": "rejected",
    "withdraw": "withdrawn",
    "withdrawn": "withdrawn",
}


def resolve_kind(raw: str) -> str:
    key = raw.strip().lower().replace(" ", "_")
    if key in config.KIND_LABELS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    known = sorted(set(list(ALIASES) + list(config.KIND_LABELS)))
    raise SystemExit(f"unknown kind {raw!r}\nknown: {', '.join(known)}")


def ts_for(day_str: str | None) -> str:
    """Now, or noon on a backfilled date."""
    if not day_str:
        return events.now_iso()
    try:
        day = date.fromisoformat(day_str)
    except ValueError:
        raise SystemExit(f"--date must be YYYY-MM-DD, got {day_str!r}")
    return datetime.combine(day, time(12, 0)).astimezone() \
        .replace(microsecond=0).isoformat()


def load_state(cfg=None) -> model.State:
    cfg = cfg or config.load()
    return model.build(events.read(), cfg)


def find_app(state: model.State, ref: str) -> model.Application:
    """Resolve an application by id prefix or company substring."""
    ref_l = ref.strip().lower()
    by_id = [a for a in state.apps.values() if a.id.startswith(ref_l)]
    if len(by_id) == 1:
        return by_id[0]
    matches = [a for a in state.apps.values() if ref_l in a.company.lower()]
    live = [a for a in matches if a.is_live]
    pool = live or matches
    if len(pool) == 1:
        return pool[0]
    if not pool:
        raise SystemExit(f"no application matching {ref!r} — try `ja list`")
    lines = "\n".join(f"  {a.id}  {a.company} — {a.role or '(no role)'}"
                      for a in pool)
    raise SystemExit(f"{ref!r} matches several applications:\n{lines}\n"
                     f"use the id instead")


# -- commands ---------------------------------------------------------------

def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        got = input(f"  {label}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\ncancelled — nothing logged")
    return got or default


def _guided_add() -> tuple[str, str, str, str]:
    """Walk through it, for when you don't want to remember the syntax."""
    print("\nLogging an application. Press Enter to accept the [default].\n")
    company = _prompt("Company")
    if not company:
        raise SystemExit("a company name is required — nothing logged")
    role = _prompt("Role", "")
    kind = _prompt("Tailored or quick? (t/q)", "t")
    kind = ("application_quick" if kind.lower().startswith("q")
            else "application_tailored")
    source = _prompt("How did you find it? cold/referral/recruiter/event", "cold")
    return company, role, kind, source


def cmd_add(args) -> None:
    raw = " ".join(args.target).strip() if args.target else ""
    if not raw:
        # No isatty() gate: guided mode should work when driven by a pipe too,
        # and _prompt already turns an immediate EOF into a clean exit.
        company, role, kind, source = _guided_add()
        _write_application(company, role, kind, source, args)
        return
    company, _, role = raw.partition("/")
    kind = "application_quick" if args.quick else "application_tailored"
    _write_application(company.strip(), role.strip(), kind, args.source, args)


def _write_application(company: str, role: str, kind: str, source: str,
                       args) -> None:
    event = {
        "id": events.new_id(events.read()),
        "ts": ts_for(getattr(args, "date", None)),
        "kind": kind,
        "company": company,
        "role": role,
        "source": source,
        "url": getattr(args, "url", "") or "",
        "notes": getattr(args, "note", "") or "",
    }
    events.append(event)
    cfg = config.load()
    pts = cfg["weights"].get(kind, 0)
    state = load_state(cfg)
    print(f"\nlogged {config.KIND_LABELS[kind].lower()} — "
          f"{company}{' / ' + role if role else ''} "
          f"(+{pts} pts, {state.points_on(state.today)}/{state.target} today)")
    print(f"  id {event['id']}   —   wrong? run:  ja undo")
    _maybe_sync(args)


def cmd_event(args) -> None:
    kind = resolve_kind(args.kind)
    state = load_state()
    event = {"ts": ts_for(args.date), "kind": kind}
    if kind in config.APPLICATION_KINDS:
        raise SystemExit("use `ja add` to log a new application")
    if args.app:
        app = find_app(state, args.app)
        event["app_id"] = app.id
        who = f" — {app.company}"
    else:
        who = ""
    events.append(event)
    cfg = config.load()
    pts = cfg["weights"].get(kind, 0)
    state = load_state(cfg)
    suffix = f"+{pts} pts, {state.points_on(state.today)}/{state.target} today" \
        if pts else "no points (that was their move, not yours)"
    print(f"logged {config.KIND_LABELS[kind].lower()}{who} ({suffix})")
    _maybe_sync(args)


def cmd_grid(args) -> None:
    state = load_state()
    if args.html:
        from . import render_html
        print(render_html.render(state, weeks=args.weeks or 26, mode=getattr(args, "mode", None)))
        return
    if args.compact:
        print(render_ansi.render_compact(state, weeks=args.weeks or 20,
                                         mode=getattr(args, "mode", None)))
        return
    print(render_ansi.render(state, weeks=args.weeks, mode=getattr(args, "mode", None)))


def cmd_stats(args) -> None:
    state = load_state()
    sch = palette.scheme(getattr(args, "mode", None))
    ink, muted = palette.fg(sch["ink"]), palette.fg(sch["muted"])
    r = palette.RESET

    def head(text):
        print(f"\n{ink}{text}{r}")

    funnel = state.funnel
    head("Pipeline")
    applied = funnel["applied"]
    for stage in config.STAGE_ORDER:
        n = funnel[stage]
        rate = f"{100 * n / applied:.0f}%" if applied else "--"
        bar = "█" * min(28, n)
        print(f"  {stage:<10} {n:>4}  {muted}{rate:>4}{r}  "
              f"{palette.fg(sch['levels'][2])}{bar}{r}")
    live = len(state.live_apps)
    cold = len(state.cold_apps)
    closed = applied - live - funnel["offer"]
    print(f"  {muted}{live - cold} active · {cold} gone cold · "
          f"{closed} closed{r}")

    head("Effort")
    print(f"  today          {state.points_on(state.today)}/{state.target} pts")
    print(f"  this week      {state.week_to_date_points()}/{state.weekly_target} pts")
    print(f"  day streak     {state.streak_days}  {muted}(best {state.best_streak_days}){r}")
    print(f"  week streak    {state.week_streak}  "
          f"{muted}(weeks at {state.weekly_target}+ pts){r}")

    if state.channels:
        head("By channel")
        print(f"  {muted}{'source':<12}{'applied':>8}{'screens':>9}{'rate':>7}{r}")
        for src, n, adv in state.channels:
            rate = f"{100 * adv / n:.0f}%" if n else "--"
            print(f"  {src:<12}{n:>8}{adv:>9}{rate:>7}")
        print(f"  {muted}referrals usually convert several times better than "
              f"cold applies{r}")

    lags = state.response_lags()
    if lags:
        head("Response lag")
        mid = lags[len(lags) // 2]
        print(f"  median {mid}d  {muted}range {lags[0]}–{lags[-1]}d{r}")
        recent = _recent_interview_lags(state)
        if recent:
            lo, hi = min(recent) // 7, max(recent) // 7
            span = f"{lo} weeks" if lo == hi else f"{lo}–{hi} weeks"
            print(f"  {muted}your last {len(recent)} interviews came from "
                  f"applications sent {span} earlier — a quiet week now is "
                  f"not a failed one{r}")

    stale = state.stale()
    if stale:
        head(f"Owed a follow-up ({len(stale)})")
        for app in stale[:8]:
            print(f"  {app.id}  {app.company:<22} "
                  f"{muted}{app.days_since_last_event(state.today)}d quiet{r}")
    print()


def _recent_interview_lags(state: model.State, limit: int = 3) -> list[int]:
    got = [(a.applied_on, a.first_response_lag) for a in state.apps.values()
           if a.stage_idx >= 1 and a.first_response_lag is not None]
    got.sort(key=lambda p: p[0], reverse=True)
    return [lag for _, lag in got[:limit]]


def cmd_stale(args) -> None:
    state = load_state()
    rows = state.stale(args.days)
    if not rows:
        print("nothing owed a follow-up — pipeline is current")
        return
    sch = palette.scheme(getattr(args, "mode", None))
    muted, r = palette.fg(sch["muted"]), palette.RESET
    for app in rows:
        quiet = app.days_since_last_event(state.today)
        print(f"{app.id}  {app.company:<24} {app.role[:28]:<28} "
              f"{muted}{quiet}d quiet · {app.stage}{r}")
    print(f"\n{muted}log one with: ja event followup --app <id>{r}")


def cmd_list(args) -> None:
    state = load_state()
    apps = sorted(state.apps.values(), key=lambda a: a.applied_on, reverse=True)
    if not args.all:
        apps = [a for a in apps if a.is_live] or apps
    sch = palette.scheme(getattr(args, "mode", None))
    muted, r = palette.fg(sch["muted"]), palette.RESET
    for app in apps[:args.limit]:
        status = app.terminal or app.stage
        print(f"{app.id}  {app.applied_on}  {app.company:<24} "
              f"{app.role[:26]:<26} {muted}{status} · {app.source}{r}")


def _confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        raise SystemExit("not a terminal — re-run with --yes to confirm")
    try:
        return input(f"{question} [y/N] ").strip().lower().startswith("y")
    except (EOFError, KeyboardInterrupt):
        return False


def cmd_undo(args) -> None:
    """Remove the most recently logged event."""
    lines = events.read_lines()
    if not lines:
        raise SystemExit("nothing logged yet")
    last = json.loads(lines[-1])
    company = ""
    if last.get("app_id"):
        app = load_state().apps.get(last["app_id"])
        company = app.company if app else ""
    print(f"about to remove:\n  {events.describe(last, company)}")
    if not _confirm("remove it?", args.yes):
        print("left alone")
        return
    events.remove_indices({len(lines) - 1})
    state = load_state()
    print(f"removed — now {state.points_on(state.today)}/{state.target} today."
          f"  put it back with:  ja restore")
    _maybe_sync(args)


def cmd_rm(args) -> None:
    """Remove an application and everything logged against it."""
    state = load_state()
    app = find_app(state, args.ref)
    lines = events.read_lines()
    indices = set()
    for i, line in enumerate(lines):
        blob = json.loads(line)
        if blob.get("id") == app.id or blob.get("app_id") == app.id:
            indices.add(i)
    plural = "s" if len(indices) != 1 else ""
    print(f"about to remove {app.company}"
          f"{' / ' + app.role if app.role else ''} "
          f"and its {len(indices)} event{plural}:")
    for i in sorted(indices):
        print(f"  {events.describe(json.loads(lines[i]), app.company)}")
    if not _confirm("remove all of it?", args.yes):
        print("left alone")
        return
    events.remove_indices(indices)
    print("removed.  put it back with:  ja restore")
    _maybe_sync(args)


def cmd_restore(args) -> None:
    back = events.restore_last()
    if not back:
        raise SystemExit("nothing to restore")
    for row in back:
        print(f"restored  {events.describe(row)}")
    _maybe_sync(args)


def cmd_on(args) -> None:
    """What did I do on a given day?"""
    from datetime import date as _date
    if args.date:
        try:
            day = _date.fromisoformat(args.date)
        except ValueError:
            raise SystemExit(f"date must be YYYY-MM-DD, got {args.date!r}")
    else:
        day = _date.today()
    state = load_state()
    rows = model.events_on(events.read(), day, state.apps)
    sch = palette.scheme(getattr(args, "mode", None))
    ink, muted, r = palette.fg(sch["ink"]), palette.fg(sch["muted"]), palette.RESET
    pts = state.points_on(day)
    print(f"\n{ink}{day.strftime('%a %-d %b %Y')}{r}"
          f"{muted}  \u2014  {pts}/{state.target} pts{r}")
    if not rows:
        print(f"{muted}  nothing logged{r}\n")
        return
    for row in rows:
        label = config.KIND_LABELS.get(row["kind"], row["kind"])
        who = row.get("company", "")
        role = row.get("role", "")
        weight = state.cfg["weights"].get(row["kind"], 0)
        badge = f"+{weight}" if weight else "  "
        name = f"{who}{' / ' + role if role else ''}" if who else ""
        print(f"  {muted}{badge}{r}  {label:<24} {name}")
    print()


def cmd_sync(args) -> None:
    from . import publish
    publish.sync(load_state(), verbose=True, init=args.init)


def cmd_phone_script(args) -> None:
    """Print the Scriptable widget with the gist URL already filled in."""
    from . import publish
    cfg = config.load()
    gist_id = cfg.get("gist_id")
    if not gist_id:
        raise SystemExit("no gist yet — run `ja sync --init` first")
    import subprocess
    user = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                          capture_output=True, text=True).stdout.strip()
    raw = (f"https://gist.githubusercontent.com/{user}/{gist_id}"
           f"/raw/{publish.GIST_FILENAME}")
    src = (config.REPO_ROOT / "widgets" / "scriptable" / "apply-grid.js").read_text()
    src = src.replace("__APPLYGRID_GIST_RAW__", raw)
    src = src.replace("__APPLYGRID_GIST_ID__", gist_id)
    sys.stdout.write(src)


def cmd_menubar(args) -> None:
    from . import menubar
    menubar.main()


def _maybe_sync(args) -> None:
    """Push to the phone after a log, unless told not to.

    A sync problem must never block logging -- but it must not be invisible
    either. Silently swallowing it is how the phone widget sat at zero while
    every Mac surface showed the right numbers.
    """
    if getattr(args, "no_sync", False):
        return
    from . import publish
    try:
        publish.sync(load_state(), verbose=False, quiet_fail=True)
    except Exception as exc:  # noqa: BLE001 - logging must still succeed
        publish._record(False, f"{type(exc).__name__}: {exc}")
    status = publish.last_status()
    if status and not status.get("ok"):
        print(f"  note: phone sync failed — {status.get('detail', '?')}")
        print("        Mac surfaces are unaffected; retry with:  ja sync")


def _add_mode(parser: argparse.ArgumentParser) -> None:
    """Allow --mode either before or after the subcommand.

    argparse.SUPPRESS is load-bearing: an ordinary default here would clobber a
    --mode already given at the top level.
    """
    parser.add_argument("--mode", choices=("dark", "light"),
                        default=argparse.SUPPRESS,
                        help="color mode (default dark)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ja", description="Apply Grid — job application effort tracker")
    p.add_argument("--mode", choices=("dark", "light"), default=None,
                   help="color mode (default dark)")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="log a new application")
    a.add_argument("target", nargs="*", metavar='"Company / Role"')
    a.add_argument("--quick", action="store_true",
                   help="a quick/easy-apply rather than a tailored one")
    a.add_argument("--tailored", action="store_true", help="(default)")
    a.add_argument("--source", default="cold",
                   help="cold / referral / recruiter / event (default cold)")
    a.add_argument("--url", default="")
    a.add_argument("--note", default="")
    a.add_argument("--date", help="backfill: YYYY-MM-DD")
    a.add_argument("--no-sync", action="store_true")
    a.set_defaults(func=cmd_add)

    e = sub.add_parser("event", help="log effort or an outcome")
    e.add_argument("kind", help="prep / followup / screen / offer / rejected ...")
    e.add_argument("--app", help="application id or company substring")
    e.add_argument("--date", help="backfill: YYYY-MM-DD")
    e.add_argument("--no-sync", action="store_true")
    e.set_defaults(func=cmd_event)

    g = sub.add_parser("grid", help="draw the contribution grid")
    g.add_argument("--weeks", type=int)
    g.add_argument("--compact", action="store_true")
    g.add_argument("--html", action="store_true")
    _add_mode(g)
    g.set_defaults(func=cmd_grid)

    s = sub.add_parser("stats", help="funnel, streaks, channels, lag")
    _add_mode(s)
    s.set_defaults(func=cmd_stats)

    st = sub.add_parser("stale", help="applications owed a follow-up")
    st.add_argument("--days", type=int)
    _add_mode(st)
    st.set_defaults(func=cmd_stale)

    ls = sub.add_parser("list", help="applications")
    ls.add_argument("--all", action="store_true", help="include closed ones")
    ls.add_argument("--limit", type=int, default=40)
    _add_mode(ls)
    ls.set_defaults(func=cmd_list)

    un = sub.add_parser("undo", help="remove the thing you just logged")
    un.add_argument("--yes", "-y", action="store_true", help="skip confirmation")
    un.add_argument("--no-sync", action="store_true")
    un.set_defaults(func=cmd_undo)

    rm = sub.add_parser("rm", help="remove an application and its events")
    rm.add_argument("ref", help="application id or company substring")
    rm.add_argument("--yes", "-y", action="store_true", help="skip confirmation")
    rm.add_argument("--no-sync", action="store_true")
    rm.set_defaults(func=cmd_rm)

    rs = sub.add_parser("restore", help="undo the last removal")
    rs.add_argument("--no-sync", action="store_true")
    rs.set_defaults(func=cmd_restore)

    on = sub.add_parser("on", help="what you did on a given day")
    on.add_argument("date", nargs="?", help="YYYY-MM-DD (default today)")
    _add_mode(on)
    on.set_defaults(func=cmd_on)

    sy = sub.add_parser("sync", help="push aggregates to the phone's gist")
    sy.add_argument("--init", action="store_true",
                    help="create the secret gist (one time, uploads to GitHub)")
    sy.set_defaults(func=cmd_sync)

    ps = sub.add_parser("phone-script",
                        help="print the Scriptable widget, URL filled in")
    ps.set_defaults(func=cmd_phone_script)

    mb = sub.add_parser("menubar", help="run the menu bar app")
    mb.set_defaults(func=cmd_menubar)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # Bare `ja` shows the thing you came to see.
        print(render_ansi.render(load_state(), mode=getattr(args, "mode", None)))
        return 0
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
