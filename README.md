# apply-grid

A GitHub-contribution-graph for job application effort, on the surfaces you
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

## Two things it does differently from GitHub's graph

**A box's darkness is weighted effort, not application count.** Counting
applications would make your darkest day the one where you fired off fifteen
Easy Applies, and would leave a day of resume tailoring or a referral ask
completely gray. Points instead (all editable in `config.json`):

| event | pts | | event | pts |
|---|---|---|---|---|
| tailored application | 3 | | follow-up | 1 |
| quick application | 1 | | interview | 5 |
| referral ask | 2 | | resume / portfolio work | 2 |
| cold outreach | 2 | | interview prep | 1 |

**Intensity scales to a daily target, not to your personal maximum.** GitHub's
scale is relative to your best-ever day, so one binge makes every ordinary day
look like a failure. Here the target is 3 pts/day and the ramp caps at 2x, so a
fifteen-application afternoon can't set an unmatchable high-water mark.

Outcomes — screens, onsites, offers, rejections — are recorded and drive the
funnel, but they are worth **zero points** and rejections never render as red
boxes. You get credit for what you did, not for what the other side decided.

## Install

```bash
./install.sh
```

It prints every change first and asks once. It creates a venv, installs the
Übersicht widget, loads a login agent for the menu bar app, and appends four
lines to `~/.zshrc`. It uploads nothing.

Prerequisites for the two widget surfaces:

- **Desktop widget**: `brew install --cask ubersicht`
- **iPhone widget**: the free [Scriptable](https://scriptable.app) app

## Usage

Day to day you'll use the menu bar item — click it, "Log tailored
application…", type `Stripe / Backend SWE`. Everything is also available from
the CLI:

```bash
ja                                  # the grid
ja add "Stripe / Backend SWE"       # a tailored application (+3)
ja add "Ramp / SWE" --quick         # an easy-apply (+1)
ja add "Figma / SWE" --source referral
ja event prep                       # standalone effort (+1)
ja event screen --app stripe        # an outcome, matched by company
ja event followup --app 7b77        # or by id
ja stats                            # funnel, streaks, channels, response lag
ja stale                            # who's owed a follow-up
```

Backfill anything with `--date 2026-09-01`.

Run `ja add` with no arguments and it walks you through it instead:

```
$ ja add
  Company: Stripe
  Role: Backend SWE
  Tailored or quick? (t/q) [t]:
  How did you find it? cold/referral/recruiter/event [cold]: referral

logged tailored application — Stripe / Backend SWE (+3 pts, 3/3 today)
  id b8bd   —   wrong? run:  ja undo
```

## Fixing mistakes

```bash
ja undo            # remove the last thing you logged (names it, then asks)
ja rm stripe       # remove an application and every event on it
ja restore         # put the last removal back
```

The same three are in the menu bar: **Undo** names exactly what it will remove,
**Remove an application** lists your recent ones, and **Restore last removal**
appears only when there's something to restore.

Nothing is destroyed. Removals are appended to `removed.jsonl` next to your log
with a batch stamp, so `restore` can put a batch back and two quick removals
stay independent.

## The phone widget

```bash
ja sync --init          # one time: creates a secret gist (this uploads)
ja phone-script | pbcopy  # paste into a new Scriptable script
```

**What gets uploaded.** A secret gist's raw URL is unguessable but
unauthenticated, so the payload is aggregates only: per-day intensity levels,
funnel counts, streaks. No company names, no roles, no URLs, no notes — and
`publish.assert_no_pii` refuses to sync if any of those keys ever appear. It's
about 600 bytes. Read `applygrid/publish.py` before trusting that claim.

Every other surface reads the log directly off your disk and uploads nothing.

## Your data, and publishing this repo

The event log is an append-only JSONL file — one object per line, never
rewritten. Everything else is a pure fold over it, so it's the only file worth
backing up, and a future email-ingester could append to it without touching a
single renderer.

**It lives outside the repo**, at `~/.local/share/apply-grid/events.jsonl`, so
the code can be public without your job search following it. Override with
`APPLYGRID_DATA`.

Two things must never be committed, and `.gitignore` covers both:

| | why |
|---|---|
| `data/` | the legacy in-repo log location, ignored so it can't be added by accident |
| `config.local.json` | holds `gist_id` — a secret gist is *unlisted, not private*, so that id is the phone widget's only access control |

`config.json` is the shareable half: point weights and targets, no secrets.

Before making the repo public, run the guards:

```bash
python3 -m unittest discover -s tests
```

`tests/test_privacy.py` fails if an event log or `config.local.json` is tracked,
if `config.json` regains a `gist_id`, if `.gitignore` stops covering those
paths, or if the sync payload ever carries a company name.

**What a public repo still reveals:** nothing about your applications — but
your commit timestamps show when you worked on the tool, and the repo name
itself says you're job searching. If that matters, keep it private.

## Colors

The ramp is a single-hue ordinal scale (OKLCH hue 142, four monotone lightness
steps), validated for monotonic lightness, adjacent step separation, single
hue, and contrast against its own surface — in both light and dark mode.

It is deliberately *not* GitHub's own green ramp: theirs fails the light-end
contrast floor (`#0e4429` is 1.69:1 on their dark surface, `#9be9a8` is 1.44:1
on white), which is why their faintest squares are so hard to tell from empty
ones. Same look, fixed floor. All four surfaces read `applygrid/palette.py`, so
they can't drift apart.

## Layout

```
applygrid/
  events.py        append-only log I/O
  model.py         the fold: points, streaks, funnel, stale, channels
  palette.py       the validated ramp — single source of color truth
  render_ansi.py   terminal
  render_menubar.py  menu bar title + dropdown
  render_html.py   Übersicht widget content
  publish.py       aggregate-only gist sync
  menubar.py       the rumps app (logging lives here)
  cli.py           `ja`
widgets/
  apply-grid.widget/   Übersicht host
  scriptable/          iPhone widget
tests/               python3 -m unittest discover -s tests
```

## Not built yet

Email ingestion is the real friction killer — your "thanks for applying"
confirmations are already a complete, automatic log of every application, which
is the one thing that would give this GitHub's actual property of costing
nothing to maintain. Same for a browser extension that fires on
Greenhouse/Lever/Workday submit pages. Both would append to the same event log.
