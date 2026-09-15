// Minimal stand-in for Scriptable's API, enough to catch runtime errors and
// verify each widget family builds and draws the expected number of cells.
//
// The phone widget is the one surface that can't be exercised from the Mac, so
// this stands in for it. Run via tests/test_widget_families.py, or directly:
//   node tests/widget_harness.mjs widgets/scriptable/apply-grid.js payload.json
//
// Expected cell counts are weeks x 7: small 84, medium/large 182,
// accessoryRectangular 119. The circular and inline families draw no grid.
import fs from "fs";

const src = fs.readFileSync(process.argv[2], "utf8");
const payload = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));

let drawn = 0, texts = [], images = 0;

class Color { constructor(hex, alpha) { this.hex = hex; this.alpha = alpha; } }
class Size  { constructor(w, h) { this.width = w; this.height = h; } }
class Rect  { constructor(x, y, w, h) { Object.assign(this, {x, y, w, h}); } }
class Path  { addRoundedRect() {} }
class DrawContext {
  constructor() { this.size = null; this.opaque = true; this.respectScreenScale = false; }
  addPath() {} setFillColor() {} fillPath() { drawn++; }
  getImage() { return { __image: true, size: this.size }; }
}
class WidgetText {
  constructor(t) { this.text = t; texts.push(t); }
  set font(v) {} set textColor(v) {} centerAlignText() {} leftAlignText() {}
}
class WidgetImage {
  applyFittingContentMode() {} centerAlignImage() {} leftAlignImage() {}
}
class WidgetStack {
  addText(t) { return new WidgetText(t); }
  addStack() { return new WidgetStack(); }
  addSpacer() {} addImage() { images++; return new WidgetImage(); }
  centerAlignContent() {} layoutVertically() {} layoutHorizontally() {}
  set spacing(v) {}
}
class ListWidget extends WidgetStack {
  set backgroundColor(v) {} setPadding() {}
}
const Font = new Proxy({}, { get: () => () => ({}) });
const Device = { isUsingDarkAppearance: () => true };
const FileManager = { local: () => ({
  joinPath: (a, b) => a + "/" + b, cacheDirectory: () => "/tmp",
  fileExists: () => false, writeString: () => {}, readString: () => "{}",
}) };
class Request {
  constructor(url) { this.url = url; }
  set headers(v) {} set timeoutInterval(v) {}
  async loadJSON() {
    if (this.url.indexOf("api.github.com") >= 0) {
      return { files: { "applygrid.json": { content: JSON.stringify(payload) } } };
    }
    return payload;
  }
}
const Script = { setWidget: () => {}, complete: () => {} };

const families = ["small", "medium", "large",
                  "accessoryRectangular", "accessoryCircular", "accessoryInline"];
let failures = 0;
for (const family of families) {
  drawn = 0; texts = []; images = 0;
  const config = { widgetFamily: family, runsInWidget: true };
  const fn = new Function(
    "Color","Size","Rect","Path","DrawContext","ListWidget","Font","Device",
    "FileManager","Request","Script","config",
    `return (async () => { ${src} })();`);
  try {
    await fn(Color, Size, Rect, Path, DrawContext, ListWidget, Font, Device,
             FileManager, Request, Script, config);
      const want = { small: 84, medium: 182, large: 182,
                   accessoryRectangular: 119, accessoryCircular: 0,
                   accessoryInline: 0 }[family];
    if (drawn !== want) {
      failures++;
      console.log(`  FAIL ${family.padEnd(21)} drew ${drawn} cells, expected ${want}`);
      continue;
    }
    console.log(`  OK   ${family.padEnd(21)} cells=${String(drawn).padStart(4)} images=${images} texts=${texts.length}`);
  } catch (err) {
    failures++;
    console.log(`  FAIL ${family.padEnd(21)} ${err.message}`);
  }
}
process.exit(failures);
