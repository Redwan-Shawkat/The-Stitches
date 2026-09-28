#!/usr/bin/env bash
# Installs Stitches for the current user: no pip, no venv —
# GTK3/PyGObject is already a system package on Ubuntu (see
# documents/ai-knowledgebase.md), so this just needs to place the source
# and wire up a launcher + app-menu entry. Re-run any time to update.
set -euo pipefail

APP_NAME="stitches"
# Must match the Gtk.Application id in gui.py — GTK's Wayland backend tags
# every window with *that* id (not the binary name), and the desktop shell
# only shows our custom icon/taskbar entry when a .desktop file of the same
# id exists.
APP_ID="io.github.stitches"
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
# Copies installed under the app's earlier names (The Uninstaller, then
# SoftHUB) go, so the app menu doesn't keep a stale entry next to this one.
for old in linux-the-uninstaller softhub; do
    rm -rf "$HOME/.local/lib/$old" "$BIN_DIR/$old"
    rm -f "$DESKTOP_DIR/io.github.$old.desktop" "$DESKTOP_DIR/$old.desktop" \
          "$ICON_DIR/io.github.$old.svg" "$ICON_DIR/$old.svg"
done
rm -rf "$LIB_DIR/stitches"
cp -r "$SRC_DIR/stitches" "$LIB_DIR/"
cp "$SRC_DIR/stitches/icon.svg" "$ICON_DIR/$APP_ID.svg"

cat > "$BIN_DIR/$APP_NAME" <<EOF
#!/usr/bin/env bash
exec env PYTHONPATH="$LIB_DIR" python3 -m stitches "\$@"
EOF
chmod +x "$BIN_DIR/$APP_NAME"

cat > "$DESKTOP_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Stitches
Comment=Update, uninstall and clean up software, update drivers, defrag drives
Exec=$BIN_DIR/$APP_NAME
Icon=$APP_ID
Terminal=false
Categories=System;Utility;
StartupWMClass=$APP_ID
EOF
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
# GTK and GNOME Shell only rescan an icon theme when its top folder changes,
# and the icon went into a subfolder: without this touch the taskbar keeps a
# generic icon until the next log in.
touch "$HOME/.local/share/icons/hicolor"
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

# A taskbar/dock pin is stored as the .desktop file's name, so removing an
# old entry above silently unpins the app. Put the new name where the old
# one was (GNOME and GNOME-based desktops; anywhere else this does nothing).
python3 - "$APP_ID.desktop" io.github.linux-the-uninstaller.desktop io.github.softhub.desktop <<'PY' || true
import ast, subprocess, sys
new, old = sys.argv[1], sys.argv[2:]
try:
    pins = ast.literal_eval(subprocess.run(["gsettings", "get", "org.gnome.shell", "favorite-apps"],
                                           capture_output=True, text=True, check=True).stdout)
except (OSError, subprocess.CalledProcessError, ValueError, SyntaxError):
    sys.exit(0)
kept = []
for pin in pins:
    pin = new if pin in old else pin
    if pin not in kept:
        kept.append(pin)
if kept != pins:
    subprocess.run(["gsettings", "set", "org.gnome.shell", "favorite-apps", str(kept)], check=False)
PY

echo "Installed: $BIN_DIR/$APP_NAME"
case ":$PATH:" in
    *":$BIN_DIR:"*) echo "Run it: $APP_NAME" ;;
    *) echo "~/.local/bin isn't on your PATH yet — open a new terminal, or run: $BIN_DIR/$APP_NAME" ;;
esac
echo "It's also in your app menu as 'Stitches' (may need a log out/in to appear)."
