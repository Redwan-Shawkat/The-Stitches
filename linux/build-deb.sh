#!/usr/bin/env bash
# Builds linux-the-uninstaller_<version>_all.deb using dpkg-deb, which every
# Debian-based system already has — no debhelper, no dh_make, no packaging
# toolchain to install. See documents/ai-knowledgebase.md ("Packaging: a
# staged tree + dpkg-deb").
set -euo pipefail

APP_NAME="linux-the-uninstaller"
# Must match the Gtk.Application id in gui.py, same reason as install.sh.
APP_ID="io.github.linux-the-uninstaller"
MAINTAINER="Redwan-Shawkat <redwanshawkat@gmail.com>"
HOMEPAGE="https://github.com/Redwan-Shawkat/The-Uninstaller"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"$/\1/p' "$ROOT/pyproject.toml")"
[ -n "$VERSION" ] || { echo "could not read version from pyproject.toml" >&2; exit 1; }

STAGE="$ROOT/dist/deb/${APP_NAME}_${VERSION}"
DEB="$ROOT/dist/${APP_NAME}_${VERSION}_all.deb"
LIB_DIR="$STAGE/usr/lib/$APP_NAME"
DOC_DIR="$STAGE/usr/share/doc/$APP_NAME"

rm -rf "$STAGE"
install -d "$STAGE/DEBIAN" "$LIB_DIR" "$STAGE/usr/bin" \
           "$STAGE/usr/share/applications" \
           "$STAGE/usr/share/icons/hicolor/scalable/apps" "$DOC_DIR"

# The app package itself. icon.svg travels with it because gui.py loads the
# window icon relative to __file__.
cp -r "$ROOT/src/uninstaller" "$LIB_DIR/"
# Ship .pyc alongside: /usr/lib isn't writable by the user running the app,
# so without these Python re-compiles on every single launch.
python3 -m compileall -q "$LIB_DIR/uninstaller" >/dev/null
cp "$ROOT/src/uninstaller/icon.svg" \
   "$STAGE/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"

cat > "$STAGE/usr/bin/$APP_NAME" <<EOF
#!/bin/sh
exec env PYTHONPATH="/usr/lib/$APP_NAME" python3 -m uninstaller "\$@"
EOF

cat > "$STAGE/usr/share/applications/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=The Uninstaller
Comment=Find and remove software regardless of how it was installed
Exec=$APP_NAME
Icon=$APP_ID
Terminal=false
Categories=System;Utility;
StartupWMClass=$APP_ID
EOF

# Policy wants both of these in /usr/share/doc/<package>.
cp "$ROOT/README.md" "$DOC_DIR/"
{
    echo "$APP_NAME ($VERSION) unstable; urgency=low"
    echo
    echo "  * Initial release."
    echo
    echo " -- ${MAINTAINER}  $(date -R)"
} | gzip -9n > "$DOC_DIR/changelog.Debian.gz"

{
    echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
    echo "Upstream-Name: $APP_NAME"
    echo "Source: $HOMEPAGE"
    echo
    echo "Files: *"
    echo "Copyright: 2026 Redwan Shawkat"
    echo "License: MIT"
    sed 's/^$/./; s/^/ /' "$ROOT/LICENSE"
} > "$DOC_DIR/copyright"

chmod -R a+rX,go-w "$STAGE"
chmod 755 "$STAGE/usr/bin/$APP_NAME"

# Must be computed before the control file that quotes it, in KiB.
INSTALLED_SIZE="$(du -ks --exclude=DEBIAN "$STAGE" | cut -f1)"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: $APP_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, pkexec | policykit-1
Maintainer: $MAINTAINER
Homepage: $HOMEPAGE
Installed-Size: $INSTALLED_SIZE
Description: find and remove software however it was installed
 One list of everything installed on a Debian-based system, whether it came
 from apt, a downloaded .deb, Snap, Flatpak, or Wine - the built-in app store
 only manages what it installed itself.
 .
 Every entry is tagged with where it came from and rated Safe, Caution or
 Critical in plain language, so it is clear what is safe to remove. Supports
 bulk uninstall behind a confirmation dialog, and finds the configuration and
 cache files a package manager leaves behind afterwards.
EOF

# --root-owner-group writes root:root ownership without needing fakeroot.
dpkg-deb --build --root-owner-group "$STAGE" "$DEB" >/dev/null
echo "Built: $DEB"
