#!/usr/bin/env bash
# Installs Linux the Uninstaller for the current user: no pip, no venv —
# GTK3/PyGObject is already a system package on Ubuntu (see
# documents/ai-knowledgebase.md), so this just needs to place the source
# and wire up a launcher + app-menu entry. Re-run any time to update.
set -euo pipefail

APP_NAME="linux-the-uninstaller"
# Must match the Gtk.Application id in gui.py — GTK's Wayland backend tags
# every window with *that* id (not the binary name), and the desktop shell
# only shows our custom icon/taskbar entry when a .desktop file of the same
# id exists.
APP_ID="io.github.linux-the-uninstaller"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/src"
LIB_DIR="$HOME/.local/lib/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

if ! python3 -c "import gi" 2>/dev/null; then
    echo "Installing python3-gi and gir1.2-gtk-3.0 (needs sudo)…"
    sudo apt-get install -y python3-gi gir1.2-gtk-3.0
fi

mkdir -p "$LIB_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"
# One-time cleanup: earlier versions named these files after $APP_NAME
# instead of $APP_ID, which is why the icon never matched.
rm -f "$DESKTOP_DIR/$APP_NAME.desktop" "$ICON_DIR/$APP_NAME.svg"
rm -rf "$LIB_DIR/uninstaller"
cp -r "$SRC_DIR/uninstaller" "$LIB_DIR/"
cp "$SRC_DIR/uninstaller/icon.svg" "$ICON_DIR/$APP_ID.svg"

cat > "$BIN_DIR/$APP_NAME" <<EOF
#!/usr/bin/env bash
exec env PYTHONPATH="$LIB_DIR" python3 -m uninstaller "\$@"
EOF
chmod +x "$BIN_DIR/$APP_NAME"

cat > "$DESKTOP_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=The Uninstaller
Comment=Find and remove software regardless of how it was installed
Exec=$BIN_DIR/$APP_NAME
Icon=$APP_ID
Terminal=false
Categories=System;Utility;
StartupWMClass=$APP_ID
EOF
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Installed: $BIN_DIR/$APP_NAME"
case ":$PATH:" in
    *":$BIN_DIR:"*) echo "Run it: $APP_NAME" ;;
    *) echo "~/.local/bin isn't on your PATH yet — open a new terminal, or run: $BIN_DIR/$APP_NAME" ;;
esac
echo "It's also in your app menu as 'The Uninstaller' (may need a log out/in to appear)."
