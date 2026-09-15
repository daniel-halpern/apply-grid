// Apply Grid — Übersicht desktop widget.
//
// Renders on the macOS desktop, behind your windows. Übersicht draws widgets
// with an internal WebKit layer, which is why the content is HTML — there is
// no browser and no URL involved.
//
// All layout comes from `ja grid --html`, so this file stays a thin host and
// the palette can't drift between surfaces.
//
// __APPLYGRID_BIN__ is substituted with an absolute path by install.sh.

export const refreshFrequency = 300000; // 5 minutes

export const command =
  "__APPLYGRID_BIN__ grid --html --weeks 26 --mode __APPLYGRID_MODE__";

export const className = `
  top: 40px;
  left: 40px;
  z-index: 0;
  -webkit-font-smoothing: antialiased;
  filter: drop-shadow(0 6px 22px rgba(0, 0, 0, 0.32));
`;

export const render = ({ output, error }) => {
  if (error) {
    return (
      <div style={{ font: "12px -apple-system", color: "#e6edf3",
                    background: "#0d1117", padding: "12px 14px",
                    borderRadius: "10px" }}>
        apply-grid: {String(error)}
      </div>
    );
  }
  // `output` is a self-contained HTML fragment with inline styles only.
  return <div dangerouslySetInnerHTML={{ __html: output }} />;
};
