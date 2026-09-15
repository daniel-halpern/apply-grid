// Apply Grid — Scriptable widget for the iPhone home or lock screen.
//
// Reads the aggregate-only snapshot your Mac pushes to a secret gist. That
// payload carries counts and intensity levels and nothing else: no company
// names, no roles, no URLs. See publish.py.
//
// Setup: paste this into a new Scriptable script named "apply-grid", set
// GIST_RAW below (or run `ja phone-script` on your Mac, which prints this file
// with the URL already filled in), then add a Scriptable widget and pick it.

const GIST_RAW = "__APPLYGRID_GIST_RAW__";

const CACHE = "apply-grid-cache.json";

// Same validated single-hue ordinal ramp as every other surface.
const RAMP = {
  dark:  { surface: "#0d1117", empty: "#21262d", ink: "#e6edf3", muted: "#8b949e",
           levels: ["#0c7202", "#439d3b", "#70ca68", "#9ef994"] },
  light: { surface: "#ffffff", empty: "#ebedf0", ink: "#1f2328", muted: "#636c76",
           levels: ["#62c958", "#4ab341", "#319c28", "#108604"] },
};

function scheme() {
  return Device.isUsingDarkAppearance() ? RAMP.dark : RAMP.light;
}

function cachePath() {
  const fm = FileManager.local();
  return fm.joinPath(fm.cacheDirectory(), CACHE);
}

async function loadData() {
  const fm = FileManager.local();
  const path = cachePath();
  try {
    const req = new Request(GIST_RAW);
    req.timeoutInterval = 8;
    const data = await req.loadJSON();
    if (!data || typeof data.levels !== "string") throw new Error("bad payload");
    fm.writeString(path, JSON.stringify(data));
    return { data, stale: false };
  } catch (err) {
    // Offline or the gist moved: show the last good snapshot rather than an
    // error, so a missing signal never reads as "you did nothing".
    if (fm.fileExists(path)) {
      return { data: JSON.parse(fm.readString(path)), stale: true };
    }
    return { data: null, stale: true };
  }
}

function levelsEndingToday(data, days) {
  const all = data.levels;
  return all.slice(Math.max(0, all.length - days));
}

function drawGrid(data, weeks, cell, gap, sch) {
  const cols = weeks;
  const width = cols * (cell + gap) - gap;
  const height = 7 * (cell + gap) - gap;
  const ctx = new DrawContext();
  ctx.size = new Size(width, height);
  ctx.opaque = false;
  ctx.respectScreenScale = true;

  // The payload ends on `today`; walk back so the last column is this week and
  // the grid aligns to Sunday exactly like the Mac and terminal versions.
  const today = new Date(data.today + "T12:00:00");
  const dow = today.getDay();                   // 0 = Sunday
  const total = cols * 7;
  const levels = levelsEndingToday(data, total - (6 - dow));

  let idx = levels.length - 1;
  for (let c = cols - 1; c >= 0; c--) {
    for (let r = 6; r >= 0; r--) {
      const isFuture = c === cols - 1 && r > dow;
      let fill = sch.empty;
      if (!isFuture) {
        const ch = idx >= 0 ? levels[idx] : "0";
        idx--;
        const lvl = parseInt(ch, 10) || 0;
        fill = lvl === 0 ? sch.empty : sch.levels[lvl - 1];
      }
      if (isFuture) continue;
      const rect = new Rect(c * (cell + gap), r * (cell + gap), cell, cell);
      const path = new Path();
      path.addRoundedRect(rect, 1.5, 1.5);
      ctx.addPath(path);
      ctx.setFillColor(new Color(fill));
      ctx.fillPath();
    }
  }
  return ctx.getImage();
}

function addRow(widget, sch, data, stale) {
  const row = widget.addStack();
  row.centerAlignContent();

  const big = row.addText(String(data.today_points));
  big.font = Font.semiboldSystemFont(20);
  big.textColor = new Color(sch.ink);

  const of = row.addText(`/${data.target} today`);
  of.font = Font.systemFont(11);
  of.textColor = new Color(sch.muted);

  row.addSpacer();

  const bits = [`${data.streak_days}d`];
  if (data.stale) bits.push(`${data.stale} to chase`);
  if (stale) bits.push("offline");
  const meta = row.addText(bits.join("  ·  "));
  meta.font = Font.systemFont(11);
  meta.textColor = new Color(sch.muted);
}

function addFunnel(widget, sch, data) {
  const line = widget.addText(
    `${data.applied} applied  ·  ${data.screens} screens` +
    (data.offers ? `  ·  ${data.offers} offer${data.offers === 1 ? "" : "s"}` : ""));
  line.font = Font.systemFont(11);
  line.textColor = new Color(sch.muted);
}

async function build() {
  const sch = scheme();
  const { data, stale } = await loadData();
  const widget = new ListWidget();
  widget.backgroundColor = new Color(sch.surface);
  widget.setPadding(12, 13, 12, 13);

  if (!data) {
    const t = widget.addText("apply-grid");
    t.font = Font.semiboldSystemFont(13);
    t.textColor = new Color(sch.ink);
    const m = widget.addText("No snapshot yet. Run `ja sync --init` on your Mac.");
    m.font = Font.systemFont(11);
    m.textColor = new Color(sch.muted);
    return widget;
  }

  const family = config.widgetFamily || "medium";
  // Fit as many weeks as the family can show, most recent last.
  const geometry = {
    small:  { weeks: 12, cell: 8,  gap: 2 },
    medium: { weeks: 26, cell: 9,  gap: 2 },
    large:  { weeks: 26, cell: 10, gap: 3 },
  }[family] || { weeks: 26, cell: 9, gap: 2 };

  addRow(widget, sch, data, stale);
  widget.addSpacer(8);
  const img = widget.addImage(
    drawGrid(data, geometry.weeks, geometry.cell, geometry.gap, sch));
  img.applyFittingContentMode();
  img.centerAlignImage();

  if (family !== "small") {
    widget.addSpacer(8);
    addFunnel(widget, sch, data);
  }
  return widget;
}

const widget = await build();
if (config.runsInWidget) {
  Script.setWidget(widget);
} else {
  widget.presentMedium();
}
Script.complete();
