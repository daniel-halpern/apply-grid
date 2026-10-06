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
# /Applications, so Spotlight and Launchpad find it and there is exactly one
# copy for macOS to grant permissions to. ~/Applications if that's not writable.
APP_DIR="/Applications"
[ -w "$APP_DIR" ] || APP_DIR="$HOME/Applications"
APP="$APP_DIR/Apply Grid.app"

say()  { printf '%s\n' "$*"; }
step() { printf '  \033[32m•\033[0m %s\n' "$*"; }

say ""
say "Apply Grid will make these changes:"
step "create the Python venv at $ROOT/.venv and install rumps"
step "build \"Apply Grid.app\" into $APP_DIR"
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
# The editor and Settings windows are Tk. Tk before 8.6.13 holds clicks and
# keystrokes on recent macOS until the mouse moves, which makes every window
# feel like it's lagging -- and it's what python.org's 3.10/3.11 builds ship.
tk_ok() {
  "$1" -c 'import sys, tkinter
v = tuple(int(x) for x in tkinter.Tcl().call("info", "patchlevel").split(".")[:3])
sys.exit(0 if v >= (8, 6, 13) else 1)' 2>/dev/null
}
pick_python() {
  for name in python3.13 python3.12 python3.14 python3; do
    for dir in /opt/homebrew/bin /usr/local/bin ""; do
      cand="${dir:+$dir/}$name"
      command -v "$cand" >/dev/null 2>&1 || continue
      "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
        2>/dev/null || continue
      tk_ok "$cand" && { echo "$cand"; return 0; }
    done
  done
  return 1
}

if [ -x "$ROOT/.venv/bin/python3" ] && ! tk_ok "$ROOT/.venv/bin/python3"; then
  if pick_python >/dev/null; then
    say "==> rebuilding the venv: its Tk is too old (windows would lag)"
    rm -rf "$ROOT/.venv"
  fi
fi
if [ ! -x "$ROOT/.venv/bin/python3" ]; then
  PYTHON="$(pick_python || true)"
  if [ -z "$PYTHON" ]; then
    PYTHON=python3
    say "==> no Python with Tk 8.6.13+ found; the windows will lag."
    say "    Fix:  brew install python-tk@3.13   then re-run this script."
  fi
  say "==> creating venv with $PYTHON"
  "$PYTHON" -m venv "$ROOT/.venv"
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

# 3. double-clickable app ---------------------------------------------------
say "==> building Apply Grid.app"
mkdir -p "$APP_DIR"
"$ROOT/build-app.sh" "$APP" >/dev/null
# Re-register so Finder and the Dock pick up a changed icon straight away.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null || true
say "    $APP  (drag it to your Dock, or find it in Spotlight)"

# 4. menu bar login agent ---------------------------------------------------
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.applygrid.menubar</string>
  <!-- The agent is the only thing that runs the menu bar app; clicking
       Apply Grid.app just kickstarts this. Two starters meant two copies,
       and on macOS 26 a copy launched from the app bundle has its menu bar
       item hidden. -->
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
    <!-- launchd's default PATH excludes Homebrew, so gh would not be found
         and the phone sync would fail on anything logged from the menu bar. -->
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
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

# 5. shell startup line -----------------------------------------------------
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
