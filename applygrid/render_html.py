"""HTML fragment for the Übersicht desktop widget.

Self-contained: inline styles only, no external CSS or fonts, because the
widget host injects this straight into its own document.
"""

from __future__ import annotations

from datetime import date

from . import config, model, palette
from .model import State

CELL = 11
GAP = 2          # the 2px surface gap that keeps adjacent fills readable
RADIUS = 2


def _tooltip(cell: model.Cell, target: int) -> str:
    when = cell.day.strftime("%a %-d %b")
    if cell.points == 0:
        return f"{when} — nothing logged"
    return f"{when} — {cell.points} pt{'s' if cell.points != 1 else ''} " \
           f"({cell.points / target:.1f}x target)"


def render(state: State, weeks: int = 26, mode: str | None = None) -> str:
    # Switched off in settings: emit nothing so the desktop widget disappears
    # without having to touch Ubersicht's own widget folder.
    if not config.surface_enabled("desktop_widget", state.cfg):
        return ""
    sch = palette.scheme(mode)
    cols = model.grid(state, weeks)
    labels = model.month_labels(cols)
    funnel = state.funnel
    stale = len(state.stale())

    width = weeks * (CELL + GAP)
    parts: list[str] = []
    parts.append(
        f'<div style="font:12px -apple-system,BlinkMacSystemFont,sans-serif;'
        f'color:{sch["ink"]};background:{sch["surface"]};padding:14px 16px;'
        f'border-radius:10px;display:inline-block">')

    # Headline numbers first: the grid is the hook, but the values have to be
    # readable as text, not only as color.
    offer_word = "offer" if funnel["offer"] == 1 else "offers"
    parts.append(
        f'<div style="display:flex;gap:14px;align-items:baseline;'
        f'margin-bottom:10px">'
        f'<span style="font-size:22px;font-weight:600">'
        f'{state.points_on(state.today)}<span style="font-size:13px;'
        f'color:{sch["muted"]};font-weight:400">/{state.target} today</span></span>'
        f'<span style="color:{sch["muted"]}">{state.streak_days}d streak</span>'
        f'<span style="color:{sch["muted"]}">{funnel["applied"]} applied</span>'
        f'<span style="color:{sch["muted"]}">{funnel["screen"]} screens</span>'
        + (f'<span style="color:{sch["muted"]}">{funnel["offer"]} {offer_word}</span>'
           if funnel["offer"] else "")
        + '</div>')

    # Month labels
    month_row = [f'<div style="position:relative;height:13px;width:{width}px;'
                 f'color:{sch["muted"]};font-size:10px">']
    for idx, name in labels.items():
        month_row.append(f'<span style="position:absolute;left:'
                         f'{idx * (CELL + GAP)}px">{name}</span>')
    month_row.append("</div>")
    parts.append("".join(month_row))

    # Grid
    parts.append(f'<div style="display:flex;gap:{GAP}px">')
    for col in cols:
        parts.append(f'<div style="display:flex;flex-direction:column;'
                     f'gap:{GAP}px">')
        for cell in col:
            if cell is None:
                parts.append(f'<div style="width:{CELL}px;height:{CELL}px"></div>')
                continue
            fill = palette.hex_for(cell.level, mode)
            parts.append(
                f'<div title="{_tooltip(cell, state.target)}" '
                f'style="width:{CELL}px;height:{CELL}px;border-radius:{RADIUS}px;'
                f'background:{fill}"></div>')
        parts.append("</div>")
    parts.append("</div>")

    # Legend
    swatches = "".join(
        f'<div style="width:{CELL}px;height:{CELL}px;border-radius:{RADIUS}px;'
        f'background:{palette.hex_for(lvl, mode)}"></div>' for lvl in range(5))
    parts.append(
        f'<div style="display:flex;align-items:center;gap:{GAP}px;'
        f'margin-top:8px;color:{sch["muted"]};font-size:10px">'
        f'<span style="margin-right:4px">Less</span>{swatches}'
        f'<span style="margin-left:4px">More</span>'
        f'<span style="margin-left:auto">target {state.target} pts/day</span>'
        f'</div>')

    if stale:
        rows = state.stale()[:3]
        names = ", ".join(a.company for a in rows)
        more = f" +{stale - len(rows)} more" if stale > len(rows) else ""
        parts.append(
            f'<div style="margin-top:10px;padding-top:9px;'
            f'border-top:1px solid {sch["empty"]};font-size:11px">'
            f'<span style="color:{palette.hex_for(3, mode)}">●</span> '
            f'<b>{stale}</b> owed a follow-up '
            f'<span style="color:{sch["muted"]}">— {names}{more}</span></div>')

    parts.append("</div>")
    return "".join(parts)
