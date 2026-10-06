# apply-grid

A GitHub contribution graph for job application effort, on the surfaces you
actually look at: the macOS **menu bar**, a **desktop widget**, an **iPhone
widget**, and your **terminal**. No website, no dashboard to remember to visit.

```
       Jun     Jul     Aug       Sep
    ██████████████████████████████████
Mon ██████████████████████████████████
    ██████████████████████████████████
Wed ██████████████████████████████████
    ...
    Less ▁▂▄▆█ More          target 3 pts/day
    4/3 today · 12d streak · 78 applied · 14 screens · 1 offer · 6 to follow up
```

In the menu bar it's one line: the last seven days, today's points against
your target, your streak, and how many applications are owed a follow-up.

```
▁▂▁█▄▁▆ 4/3 ·12d ·6↻
```

## What a square means

**A square's shade is weighted effort, not application count.** Counting
applications would make your darkest day the one where you fired off fifteen
Easy Applies, and would leave a day of resume tailoring or a referral ask
completely gray. Points instead:

| event | pts | | event | pts |
|---|---|---|---|---|
| tailored application | 3 | | follow-up | 1 |
| quick application | 1 | | interview | 5 |
| online assessment / video | 3 | | resume / portfolio work | 2 |
| referral ask | 2 | | interview prep | 1 |
| cold outreach | 2 | | | |

**Shades are relative to your own busy days**, the way GitHub's are, so the
grid always uses its full range: quiet days are pale, your biggest days are
dark. "Busy" means your top 10% of days over the past year rather than your
single best one, so one fifteen-application afternoon can't wash every other
day out to the palest green. If you'd rather be measured against a fixed goal,
Settings → Colour switches to scaling against your daily target.

**Outcomes earn nothing.** Screens, onsites, offers and rejections are recorded
and drive the funnel, but they're worth zero points, and a rejection never
shows up as a red square. You get credit for what you did, not for what the
other side decided.

## Requirements

- macOS 12 or later
- Python 3.10+ with Tk 8.6.13 or newer. Older Tk, which python.org's 3.10
  and 3.11 installers ship, holds clicks and keystrokes in the windows until
  the mouse moves, so everything feels laggy. The easy route is Homebrew:
  `brew install python-tk@3.13`. `install.sh` picks a suitable Python for you
  and says so if it can't find one.
- For the desktop widget: [Übersicht](https://tracesof.net/uebersicht/),
  `brew install --cask ubersicht`
- For the iPhone widget: the free [Scriptable](https://scriptable.app) app, and
  the [GitHub CLI](https://cli.github.com) signed in (`gh auth login`) to sync
  to it

## Install

```bash
git clone https://github.com/daniel-halpern/apply-grid.git
cd apply-grid
./install.sh
```

It prints every change it will make and asks once before touching anything:

- creates a venv in the project folder and installs `rumps`
- builds **Apply Grid.app** into `/Applications` (or `~/Applications`)
- installs the Übersicht desktop widget, if Übersicht is installed
- loads a login agent so the menu bar app starts when you log in
- adds four lines to `~/.zshrc` that put `ja` on your PATH and print the grid
  in new terminals

It uploads nothing. The phone sync is a separate step (below), because that
one does send data to GitHub.

**If the project lives in Documents, Desktop or Downloads**, macOS won't let
the app read it until you allow it: System Settings → Privacy & Security →
Full Disk Access → **+** → Apply Grid. The app tells you when this is the
problem. Cloning somewhere like `~/Developer` avoids it entirely.

## Day to day

Click the menu bar item:

- **Log tailored application…** / **Log quick application…**: type
  `Stripe / Backend SWE`. It's recorded as coming from your usual source
  (LinkedIn unless you change it in Settings); add `@linkedin`, `@portal`,
  `@uni`, `@referral` or `@recruiter` when it came from somewhere else.
- **Log online assessment**: pick the application. Being sent an OA or a
  video interview means you got past the first filter, so this also marks
  that application as screened. No second entry needed.
- **Log effort**: prep, resume work, a referral ask, an interview. Hide the
  ones you never do in Settings.
- **Follow up on**: applications that have gone quiet. Click one to log the
  follow-up.
- **Record an outcome…**: a screen, an onsite, an offer, a rejection.
- **What did I do on…**: the question a green square makes you ask. Pick a day
  to see exactly what you logged.
- **Edit entries…**: a window listing every entry, sortable and filterable,
  where you can fix any field.

The menu bar app has no Dock icon. Opening **Apply Grid** from the Dock,
Spotlight or Launchpad starts it if it isn't already running, and there's only
ever one copy. **Quit** stops it until your next login, or until you open it
again.

### From the terminal

```bash
ja                                  # the grid
ja add "Stripe / Backend SWE"       # a tailored application (+3)
ja add "Ramp / SWE" --quick         # an easy apply (+1)
ja add "Figma / SWE @uni"           # found it on your uni's job portal
ja add "Figma / SWE" --source referral
ja add                              # no arguments: asks you step by step
ja event prep                       # standalone effort (+1)
ja event oa --app doordash          # an online assessment (+3), marks it screened
ja event screen --app stripe        # an outcome, matched by company
ja event followup --app 7b77        # ...or by id
ja on 2026-09-01                    # what you did that day
ja stats                            # funnel, streaks, channels, response lag
ja stale                            # who's owed a follow-up
ja list                             # every application
ja edit                             # the editor window
```

Backfill anything with `--date 2026-09-01`.

If something seems off:

```bash
ja status      # is the menu bar app running, is the phone current
ja restart     # restart the menu bar app
```

## Fixing mistakes

```bash
ja undo            # remove the last thing you logged (names it, then asks)
ja rm stripe       # remove an application and every event on it
ja restore         # put the last removal back
```

The same three are in the menu bar. **Undo** names exactly what it will
remove, **Remove an application** lists your recent ones, and **Restore last
removal** appears only when there's something to restore. For anything else,
like a typo in a company name or the wrong date, use **Edit entries…**.

Nothing is destroyed. Removed and edited entries are kept in `removed.jsonl`
next to your log, so `restore` can put them back.

## Settings

**Settings…** in the menu bar. Changes apply as you make them; there's no Save
button.

- **Surfaces**: turn off the desktop widget, the terminal grid or the phone
  sync independently.
- **Logging**: where you usually find jobs (LinkedIn, a job portal, your
  uni's portal, ...), so most entries need no tag, and which efforts appear
  under Log effort.
- **Colour**: shade against your busy days or against your daily target, and
  light, dark or follow-the-system colours. In light mode darker green means
  more; in dark mode, as on GitHub, brighter green does.
- **Grid layout**: `today` (the default) puts today in the bottom-right corner
  with no gaps. `sunday` is GitHub's exact layout, which leaves a notch for the
  rest of the current week.
- **Daily nudge**: see below.
- **Targets**: points for a full day, good days per week, and when a quiet
  application should be chased and when it counts as gone cold.

Settings are saved to `config.local.json`, which is per-machine and never
committed. `config.json` holds the shared defaults, including the point
weights.

## The daily nudge

One evening notification, designed to avoid the usual fate of reminders,
which is getting ignored and then muted:

- **It only fires when it can change something.** Once you've hit today's
  target it stays silent, so on a good week you get none at all.
- **It has a budget:** at most one a day and three a week, and only between
  6 and 9pm by default.
- **It tells you something you don't already know**: a named application
  that's owed a follow-up, a streak about to break, a week within reach. It
  doesn't repeat the same kind of message twice running.
- **It backs off.** Ignore three in a row and it pauses for a week.
- **It never guilts you.** No "you did nothing today."

## The phone widget

```bash
ja sync --init            # one time: creates a secret gist (this uploads)
ja phone-script | pbcopy  # copy the widget, with your gist filled in
```

In Scriptable, make a new script, paste, and run it once. Then add a
Scriptable widget to your home screen and pick the script. Small, medium and
large sizes all work, and so does the lock screen's rectangular slot.

After that the phone keeps itself current. The Mac pushes after everything you
log, and every few hours on days you don't log anything, so the grid keeps
moving through a quiet stretch. iOS refreshes widgets on its own schedule, so
expect the phone to trail your Mac by a few minutes.

When you update apply-grid, run `ja phone-script | pbcopy` again and paste
over the old script: the colours and layout live in the script itself.

**What gets uploaded.** A secret gist's URL is unguessable, but anyone who has
it can read it without logging in, so the payload is aggregates only: one
shade per day, funnel counts, streaks. No company names, roles, URLs or notes,
and `publish.assert_no_pii` refuses to sync if any of those ever appear. It's
about 600 bytes. Read `applygrid/publish.py` before trusting that claim.

Every other surface reads the log directly off your disk and uploads nothing.

## Your data

Everything you log goes into one append-only file,
`~/.local/share/apply-grid/events.jsonl`, one JSON object per line. Every
number on every surface is computed from it, so it's the only file worth
backing up. Each write is on disk before it returns, so a crash or a power cut
can't cost you more than the entry in flight. Override the location with
`APPLYGRID_DATA`.

**It lives outside the repo**, so the code can be public without your job
search following it. Two things must never be committed, and `.gitignore`
covers both:

| | why |
|---|---|
| `data/` | an older in-repo log location, ignored so it can't be added by accident |
| `config.local.json` | holds `gist_id`. A secret gist is *unlisted, not private*, so that id is the phone widget's only access control |

Run the tests before pushing anything:

```bash
python3 -m unittest discover -s tests
```

`tests/test_privacy.py` fails if an event log or `config.local.json` is
tracked, if `config.json` gains a `gist_id`, if `.gitignore` stops covering
those paths, or if the sync payload ever carries a company name.

## Colours

GitHub's own contribution-graph greens, in light and dark mode. Every surface
reads them from `applygrid/palette.py`, and a test checks that the phone
widget's copy matches, so they can't drift apart.

## Code

```
applygrid/
  events.py          append-only log: read, append, remove, restore
  model.py           the fold: points, shades, streaks, funnel, follow-ups
  config.py          shared defaults + per-machine overrides
  palette.py         the colours, single source of truth
  render_ansi.py     terminal grid
  render_menubar.py  menu bar title and dropdown
  render_html.py     Übersicht widget content
  menubar.py         the menu bar app (logging lives here)
  editor.py          Edit entries window
  settings.py        Settings window
  window.py          shared window behaviour
  background.py      phone sync off the UI thread
  nudge.py           when to nudge, and what to say
  notify.py          macOS notifications
  publish.py         aggregate-only gist sync
  process.py         keeps it to one running copy
  cli.py             `ja`
bin/
  ja                 CLI entry point
  ja-startup         fast path for the terminal grid
  app-launcher       Apply Grid.app's executable
widgets/
  apply-grid.widget/ Übersicht host
  scriptable/        iPhone widget
build-app.sh         builds Apply Grid.app (no Xcode needed)
make-icon.py         draws the app icon from palette.py
install.sh
tests/               python3 -m unittest discover -s tests
```

## Not built yet

Email ingestion is the real friction killer. Your "thanks for applying"
confirmations are already a complete, automatic log of every application,
which would give this GitHub's real advantage: costing nothing to maintain.
Same for a browser extension that fires on Greenhouse, Lever and Workday
submit pages. Both would append to the same event log.

## License

[MIT](LICENSE)
