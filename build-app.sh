#!/bin/bash
# Build "Apply Grid.app" — a double-clickable launcher for the menu bar app.
#
# No Xcode required: a .app is just a folder with an Info.plist and an
# executable. The ad-hoc signature (`codesign -s -`) is what lets Finder and
# `open` launch it at all; without one macOS refuses with "no usable signature".
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="${1:-$ROOT/Apply Grid.app}"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Apply Grid</string>
  <key>CFBundleDisplayName</key><string>Apply Grid</string>
  <key>CFBundleIdentifier</key><string>com.applygrid.menubar</string>
  <key>CFBundleExecutable</key><string>apply-grid</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <!-- Menu bar only: no Dock icon, no window on launch. -->
  <key>LSUIElement</key><true/>
  <key>NSDocumentsFolderUsageDescription</key>
  <string>Apply Grid reads its own project folder to run.</string>
</dict>
</plist>
PLIST

cp "$ROOT/bin/app-launcher" "$APP/Contents/MacOS/apply-grid"
/usr/bin/sed -i '' "s|__APPLYGRID_ROOT__|$ROOT|g" "$APP/Contents/MacOS/apply-grid"
chmod +x "$APP/Contents/MacOS/apply-grid"

codesign --force --deep --sign - "$APP"
echo "built and signed: $APP"

# Folders macOS protects. Code run from one of these is unreadable to an app
# bundle until the user grants access by hand, which is a poor experience and
# does not travel to anyone you share this with.
case "$ROOT" in
  "$HOME/Documents"/*|"$HOME/Desktop"/*|"$HOME/Downloads"/*)
    cat <<WARN

  NOTE: this project lives in a macOS-protected folder:
    $ROOT

  The app cannot read it until you allow it:
    System Settings > Privacy & Security > Full Disk Access > + > "Apply Grid.app"

  Moving the project somewhere like ~/Developer avoids this entirely.
WARN
    ;;
esac
