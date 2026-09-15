#!/bin/bash
# Apply Grid installer. Prints every change it intends to make, then asks once.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
JA="$ROOT/bin/ja"
MODE="${APPLYGRID_MODE:-dark}"
UB_WIDGETS="$HOME/Library/Application Support/Übersicht/widgets"
AGENT="$HOME/Library/LaunchAgents/com.applygrid.menubar.plist"
ZSHRC="$HOME/.zshrc"
ZMARK="# >>> apply-grid >>>"

say()  { printf '%s\n' "$*"; }
step() { printf '  \033[32m•\033[0m %s\n' "$*"; }

say ""
say "Apply Grid will make these changes:"
step "create the Python venv at $ROOT/.venv and install rumps"
step "install the Übersicht widget into:"
say  "      $UB_WIDGETS/apply-grid.widget/"
step "install a login agent so the menu bar app starts automatically:"
say  "      $AGENT"
step "append 4 lines to $ZSHRC (between '$ZMARK' markers)"
say ""
say "It will NOT upload anything. The phone sync is a separate, explicit step"
say "(\`ja sync --init\`), because that one does push data to GitHub."
say ""
read -r -p "Proceed? [y/N] " reply
[[ "$reply" == [yY] ]] || { say "nothing changed."; exit 0; }

# 1. venv -------------------------------------------------------------------
if [ ! -x "$ROOT/.venv/bin/python3" ]; then
  say "==> creating venv"
  python3 -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$ROOT/.venv/bin/pip" install --quiet rumps
say "==> venv ready"

# 2. Übersicht widget -------------------------------------------------------
# Übersicht may be installed but never launched, in which case its support
# directory doesn't exist yet -- so key off the app, and create the dir.
if [ -d "/Applications/Übersicht.app" ] || [ -d "$UB_WIDGETS" ]; then
  mkdir -p "$UB_WIDGETS/apply-grid.widget"
  sed -e "s|__APPLYGRID_BIN__|$JA|g" -e "s|__APPLYGRID_MODE__|$MODE|g" \
    "$ROOT/widgets/apply-grid.widget/index.jsx" \
    > "$UB_WIDGETS/apply-grid.widget/index.jsx"
  say "==> Übersicht widget installed"
  # -x fails on the non-ASCII process name; match the bundle path instead.
  if ! pgrep -qf "Übersicht.app" 2>/dev/null; then
    say "    Übersicht isn't running yet — open it once (it lives in the menu"
    say "    bar) and the widget appears on your desktop."
  else
    say "    it appears within 5 min, or now via Übersicht > Refresh All Widgets"
  fi
else
  say "==> Übersicht not found — install it first, then re-run this script:"
  say "      brew install --cask ubersicht"
fi

# 3. menu bar login agent ---------------------------------------------------
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.applygrid.menubar</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/.venv/bin/python3</string>
    <string>-m</string>
    <string>applygrid.menubar</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key><string>$ROOT</string>
    <key>APPLYGRID_MODE</key><string>$MODE</string>
  </dict>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>/tmp/applygrid.menubar.log</string>
</dict>
</plist>
PLIST
launchctl unload "$AGENT" 2>/dev/null || true
launchctl load "$AGENT"
say "==> menu bar app loaded (and will start at login)"

# 4. shell startup line -----------------------------------------------------
if ! grep -qF "$ZMARK" "$ZSHRC" 2>/dev/null; then
  cat >> "$ZSHRC" <<ZEOF

$ZMARK
export PATH="$ROOT/bin:\$PATH"
[[ \$- == *i* ]] && "$ROOT/bin/ja-startup"
# <<< apply-grid <<<
ZEOF
  say "==> added the startup grid to $ZSHRC"
else
  say "==> $ZSHRC already wired up, left alone"
fi

say ""
say "Done. Try:  ja add \"Stripe / Backend SWE\""
say "Phone widget (optional, uploads aggregates to a secret gist):"
say "  ja sync --init && ja phone-script | pbcopy"
say ""
