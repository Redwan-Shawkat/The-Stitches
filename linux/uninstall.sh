#!/usr/bin/env bash
# Removes what install.sh placed. Fitting that this project has one.
set -euo pipefail

APP_NAME="linux-the-uninstaller"
APP_ID="io.github.linux-the-uninstaller"
rm -rf "$HOME/.local/lib/$APP_NAME"
rm -f "$HOME/.local/bin/$APP_NAME"
rm -f "$HOME/.local/share/applications/$APP_ID.desktop" "$HOME/.local/share/applications/$APP_NAME.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_NAME.svg"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Removed $APP_NAME."
