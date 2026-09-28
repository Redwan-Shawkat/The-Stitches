#!/usr/bin/env bash
# Builds the release APK: Stitches-<version>.apk.
#
# A release APK has to be signed or Android won't install it, so this creates
# a local keystore on first run rather than handing you an unsigned artifact.
# CI signs with a keystore from secrets instead — see
# .github/workflows/android-build.yml and documents/ai-knowledgebase.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^ *versionName = "\(.*\)"$/\1/p' app/build.gradle.kts)"
[ -n "$VERSION" ] || { echo "could not read versionName from app/build.gradle.kts" >&2; exit 1; }

KEYSTORE="$ROOT/keystore.jks"
PROPS="$ROOT/keystore.properties"

if [ ! -f "$PROPS" ]; then
  echo "No keystore.properties — generating a local signing key."
  echo "Keep $KEYSTORE: Android only accepts updates signed with the same key."
  PASSWORD="$(head -c 24 /dev/urandom | base64 | tr -d '/+=')"
  keytool -genkeypair -keystore "$KEYSTORE" -storepass "$PASSWORD" -keypass "$PASSWORD" \
    -alias uninstaller -keyalg RSA -keysize 4096 -validity 10000 \
    -dname "CN=Stitches, O=Stitches, C=US" >/dev/null
  cat > "$PROPS" <<PROPS_EOF
storeFile=keystore.jks
storePassword=$PASSWORD
keyAlias=uninstaller
keyPassword=$PASSWORD
PROPS_EOF
  chmod 600 "$PROPS" "$KEYSTORE"
fi

./gradlew --console=plain test assembleRelease

APK="$ROOT/app/build/outputs/apk/release/app-release.apk"
[ -f "$APK" ] || { echo "gradle produced no signed APK at $APK" >&2; exit 1; }

mkdir -p "$ROOT/dist"
OUT="$ROOT/dist/Stitches-$VERSION.apk"
cp "$APK" "$OUT"
( cd "$ROOT/dist" && sha256sum "$(basename "$OUT")" > SHA256SUMS.txt )

echo
echo "$OUT"
cat "$ROOT/dist/SHA256SUMS.txt"
