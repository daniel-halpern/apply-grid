// Apply Grid -- Scriptable widget for the iPhone home or lock screen.
//
// Reads the aggregate-only snapshot your Mac pushes to a secret gist. That
// payload carries counts and intensity levels and nothing else: no company
// names, no roles, no URLs. See publish.py.
//
// Setup: paste this into a new Scriptable script named "apply-grid", set
// GIST_RAW below (or run `ja phone-script` on your Mac, which prints this file
// with the URL already filled in), then add a Scriptable widget and pick it.

// Filled in by `ja phone-script` on your Mac.
const GIST_ID = "__APPLYGRID_GIST_ID__";
const GIST_RAW = "__APPLYGRID_GIST_RAW__";

// The API copy is cached for 60s; the raw CDN copy for 300s and a query string
// does not bust it. So try the API first and keep raw as a fallback -- an
// unauthenticated gist read is 1 of 60 requests/hour, and this refreshes far
// less often than that.
const GIST_API = "https://api.github.com/gists/" + GIST_ID;

const CACHE = "apply-grid-cache.json";

// Same validated single-hue ordinal ramp as every other surface.
const RAMP = {
  dark:  { surface: "#0d1117", empty: "#21262d", ink: "#e6edf3", muted: "#8b949e",
           levels: ["#0c7202", "#439d3b", "#70ca68", "#9ef994"] },
  light: { surface: "#ffffff", empty: "#ebedf0", ink: "#1f2328", muted: "#636c76",
           levels: ["#62c958", "#4ab341", "#319c28", "#108604"] },
};

function scheme(data) {
  // A pinned scheme travels in the payload and wins. In the light ramp darker
  // green means more; the dark ramp brightens instead, because on a near-black
  // surface darker tends toward invisible.
  const pinned = data && data.scheme;
  if (pinned === "light") return RAMP.light;
  if (pinned === "dark") return RAMP.dark;
  return Device.isUsingDarkAppearance() ? RAMP.dark : RAMP.light;
}

function cachePath() {
  const fm = FileManager.local();
  return fm.joinPath(fm.cacheDirectory(), CACHE);
}

async function fetchJSON(url, transform) {
  const req = new Request(url);
  req.timeoutInterval = 8;
  req.headers = { "Accept": "application/vnd.github+json" };
  const body = await req.loadJSON();
  const data = transform ? transform(body) : body;
  if (!data || typeof data.levels !== "string") throw new Error("bad payload");
  return data;
}

async function loadData() {
  const fm = FileManager.local();
  const path = cachePath();
  const attempts = [
    // Freshest first.
    () => fetchJSON(GIST_API, (b) => {
      const file = b.files && Object.values(b.files)[0];
      if (!file || !file.content) throw new Error("no gist file");
      return JSON.parse(file.content);
    }),
    () => fetchJSON(GIST_RAW),
  ];
  for (const attempt of attempts) {
    try {
      const data = await attempt();
      fm.writeString(path, JSON.stringify(data));
      return { data, stale: false };
    } catch (err) {
      // try the next source
    }
  }
  // Offline, or the gist moved: show the last good snapshot rather than an
  // error, so a missing signal never reads as "you did nothing".
  if (fm.fileExists(path)) {
    return { data: JSON.parse(fm.readString(path)), stale: true };
  }
  return { data: null, stale: true };
}

function startOfDay(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12);
}

// Whole days between the snapshot and the phone's own today. The Mac only
// pushes when something happens or on a timer, so a sleeping laptop leaves the
// payload behind -- without this the grid would freeze on the snapshot's date
// and "today" would point at the wrong square.
function driftDays(data) {
  if (!data || !data.today) return 0;
  const snapshot = startOfDay(new Date(data.today + "T12:00:00"));
  const today = startOfDay(new Date());
  const days = Math.round((today - snapshot) / 86400000);
  return days > 0 ? Math.min(days, 370) : 0;
}

// Extend the history with empty days so the grid still ends on the real today.
// Unknown days render as empty, which is also what they mean: nothing reached
// the phone for them.
function withDrift(data, drift) {
  if (!drift) return data;
  return Object.assign({}, data, { levels: data.levels + "0".repeat(drift) });
}

function levelsEndingToday(data, days) {
  let out = data.levels.slice(Math.max(0, data.levels.length - days));
  while (out.length < days) out = "0" + out;   // payload shorter than the grid
  return out;
}

function fillCell(ctx, c, r, cell, gap, color) {
  const rect = new Rect(c * (cell + gap), r * (cell + gap), cell, cell);
  const path = new Path();
  path.addRoundedRect(rect, 1.5, 1.5);
  ctx.addPath(path);
  ctx.setFillColor(color);
  ctx.fillPath();
}

// Lock screen widgets are rendered monochrome and tinted by the system, so a
// green ramp flattens to one shade there. Carry intensity in alpha instead.
const MONO_ALPHA = [0.18, 0.45, 0.65, 0.82, 1.0];

function drawGrid(rawData, weeks, cell, gap, sch, mono, offsetWeeks) {
  const drift = driftDays(rawData);
  const data = withDrift(rawData, drift);
  const cols = weeks;
  const ctx = new DrawContext();
  ctx.size = new Size(cols * (cell + gap) - gap, 7 * (cell + gap) - gap);
  ctx.opaque = false;
  ctx.respectScreenScale = true;

  const shade = (ch) => {
    const lvl = parseInt(ch, 10) || 0;
    if (mono) return new Color("#ffffff", MONO_ALPHA[lvl]);
    return new Color(lvl === 0 ? sch.empty : sch.levels[lvl - 1]);
  };

  // The layout comes from the payload so the phone can't drift from the Mac.
  if ((data.anchor || "today") === "today") {
    // Solid rectangle: the last cell is today, nothing is ever blank.
    // offsetWeeks shifts the window back, so two grids can stack into a year.
    const back = (offsetWeeks || 0) * 7;
    const window = back
      ? { levels: data.levels.slice(0, Math.max(0, data.levels.length - back)),
          anchor: "today" }
      : data;
    const levels = levelsEndingToday(window, cols * 7);
    for (let c = 0; c < cols; c++) {
      for (let r = 0; r < 7; r++) {
        fillCell(ctx, c, r, cell, gap, shade(levels[c * 7 + r]));
      }
    }
    return ctx.getImage();
  }

  // Sunday-anchored: row 0 is Sunday and the rest of this week stays blank.
  const today = startOfDay(drift ? new Date()
                                 : new Date(data.today + "T12:00:00"));
  const dow = today.getDay();
  const levels = levelsEndingToday(data, cols * 7 - (6 - dow));
  let idx = levels.length - 1;
  for (let c = cols - 1; c >= 0; c--) {
    for (let r = 6; r >= 0; r--) {
      if (c === cols - 1 && r > dow) continue;      // future: leave blank
      fillCell(ctx, c, r, cell, gap, shade(idx >= 0 ? levels[idx] : "0"));
      idx--;
    }
  }
  return ctx.getImage();
}

function addRow(widget, sch, data, stale) {
  const row = widget.addStack();
  row.centerAlignContent();

  // Nothing has reached the phone for today, so today's total is unknown --
  // showing the snapshot's figure would label an old day as today.
  const drift = driftDays(data);
  const big = row.addText(String(drift ? 0 : data.today_points));
  big.font = Font.semiboldSystemFont(20);
  big.textColor = new Color(sch.ink);

  const of = row.addText(`/${data.target} today`);
  of.font = Font.systemFont(11);
  of.textColor = new Color(sch.muted);

  row.addSpacer();

  const bits = [];
  if (!drift) bits.push(`${data.streak_days}d`);
  if (data.stale) bits.push(`${data.stale} to chase`);
  if (drift) {
    const when = new Date(data.today + "T12:00:00");
    const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][when.getMonth()];
    bits.push(`as of ${when.getDate()} ${month}`);
  }
  if (stale) bits.push("offline");
  const meta = row.addText(bits.join("  \u00B7  "));
  meta.font = Font.systemFont(11);
  meta.textColor = new Color(sch.muted);
}

function addFunnel(widget, sch, data) {
  const line = widget.addText(
    `${data.applied} applied  \u00B7  ${data.screens} screens` +
    (data.offers ? `  \u00B7  ${data.offers} offer${data.offers === 1 ? "" : "s"}` : ""));
  line.font = Font.systemFont(11);
  line.textColor = new Color(sch.muted);
}

const GEOMETRY = {
  // weeks x (cell+gap) - gap must stay just under the inner width, or iOS
  // scales the image down and the grid looks smaller than its box.
  small:                { weeks: 12, cell: 8, gap: 2 },   // 118 of 132pt
  medium:               { weeks: 26, cell: 9, gap: 2 },   // 284 of 312pt
  large:                { weeks: 26, cell: 10, gap: 2 },  // 310 of 312pt, x2
  accessoryRectangular: { weeks: 21, cell: 6, gap: 1 },   // 146 of ~152pt
};

function emptyState(widget, sch, lock) {
  const t = widget.addText("apply-grid");
  t.font = Font.semiboldSystemFont(lock ? 11 : 13);
  if (!lock) t.textColor = new Color(sch.ink);
  const m = widget.addText(
    lock ? "no data yet" : "No snapshot yet. Run `ja sync --init` on your Mac.");
  m.font = Font.systemFont(lock ? 10 : 11);
  if (!lock) m.textColor = new Color(sch.muted);
  return widget;
}

function addStats(widget, sch, data) {
  const bits = [
    `${data.streak_days}d streak`,
    `best ${data.best_streak_days}d`,
    `${data.active} active`,
  ];
  if (data.stale) bits.push(`${data.stale} to chase`);
  const line = widget.addText(bits.join("  \u00B7  "));
  line.font = Font.systemFont(11);
  line.textColor = new Color(sch.muted);
}

async function build() {
  const { data, stale } = await loadData();
  const sch = scheme(data);
  const widget = new ListWidget();
  const family = config.widgetFamily || "medium";
  const lock = family.indexOf("accessory") === 0;

  if (lock) {
    // The system owns the background and tint on the lock screen; setting a
    // background colour here is ignored at best and muddy at worst.
    try { widget.addAccessoryWidgetBackground = true; } catch (e) {}
    widget.setPadding(2, 4, 2, 4);
  } else {
    widget.backgroundColor = new Color(sch.surface);
    widget.setPadding(12, 13, 12, 13);
  }

  if (!data) return emptyState(widget, sch, lock);

  // One line of text, no room for a grid.
  if (family === "accessoryInline") {
    widget.addText(
      `${data.today_points}/${data.target} today \u00B7 ${data.streak_days}d`);
    return widget;
  }

  // A small circle: the numbers only.
  if (family === "accessoryCircular") {
    const stack = widget.addStack();
    stack.layoutVertically();
    stack.centerAlignContent();
    const big = stack.addText(String(data.today_points));
    big.font = Font.boldSystemFont(18);
    big.centerAlignText();
    const sub = stack.addText(`of ${data.target}`);
    sub.font = Font.systemFont(9);
    sub.centerAlignText();
    return widget;
  }

  const geometry = GEOMETRY[family] || GEOMETRY.medium;

  if (family === "accessoryRectangular") {
    const head = widget.addText(
      `${data.today_points}/${data.target} today` +
      `  \u00B7  ${data.streak_days}d` +
      (data.stale ? `  \u00B7  ${data.stale} to chase` : ""));
    head.font = Font.systemFont(10);
    widget.addSpacer(3);
    const img = widget.addImage(drawGrid(
      data, geometry.weeks, geometry.cell, geometry.gap, sch, true));
    img.applyFittingContentMode();
    img.leftAlignImage();
    return widget;
  }

  addRow(widget, sch, data, stale);

  const addGrid = (offsetWeeks) => {
    const img = widget.addImage(drawGrid(
      data, geometry.weeks, geometry.cell, geometry.gap, sch, false,
      offsetWeeks));
    img.applyFittingContentMode();
    img.centerAlignImage();
  };

  if (family === "large") {
    // A 7-row grid leaves more than half of a large box empty, so show a full
    // year as two stacked half-years and let flexible spacers spread it out.
    widget.addSpacer();
    addGrid(geometry.weeks);          // the older half
    widget.addSpacer(4);
    addGrid(0);                       // the recent half, ending today
    widget.addSpacer();
    addFunnel(widget, sch, data);
    addStats(widget, sch, data);
    return widget;
  }

  widget.addSpacer(8);
  addGrid(0);

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
