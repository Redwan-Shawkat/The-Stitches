# Stitches for Android

The Android build of [Stitches](../README.md). The gap here is a
different shape from the Linux and Windows ones, and worth stating honestly:
Settings › Apps *does* list everything installed. What it won't tell you is
where any of it came from. A sideloaded APK, a Play install, an F-Droid
install and something the manufacturer preloaded all look identical in that
list, and finding out means opening each app's page and scrolling. There's no
bulk uninstall, nothing warns you that the app you're about to remove is your
keyboard, and nothing cleans up the folder an app left at the top of your
storage.

This is one list for all of it — tagged by how it got onto your phone, tagged
Safe/Caution/Critical to remove in plain language, with bulk uninstall and
leftover-file cleanup.

It looks like the Linux build: a dock along the bottom (the sewn logo is
**Home**, then **Uninstall**, then theme and optional access), a dark action
bar on each page with a thin line that sweeps while it looks and fills as it
removes, round ticks, and coloured tags. Four themes, as on Linux: Light,
Dark, AMOLED (pure black) and Glass (your wallpaper shows through). It starts
in whichever of Light and Dark your phone is set to.

## What it detects

| Tag | What it means |
|---|---|
| **Play Store** | Installed by the Play Store. |
| **F-Droid** | Installed by F-Droid — invisible to Play's own "my apps" list. |
| **Other app store** | Galaxy Store, Amazon, AppGallery, Aurora, a vendor store; the installing package is shown for anything unrecognised. |
| **Sideloaded APK** | Installed by tapping an APK file, or over `adb`. |
| **Preinstalled** | Shipped with the device. Android won't fully remove these — only disable them. |

Each item is also rated:

- 🟢 **Safe** — a standalone app; removing it only removes that app.
- 🟡 **Caution** — preinstalled, or a background app with no icon that
  something else may be relying on; read the reason shown before removing.
- 🔴 **Critical** — your home screen, your active keyboard, a device
  administrator, or part of Android itself; never ticked by the select-all
  circle.

Three of those signals are things Android will answer directly rather than
guesses: which package is the home screen, which ones hold device-admin
rights, and which keyboard is active.

**Home** (the logo in the dock): the phone's model, Android version, build and
kernel, then whether Android's own boot-time integrity check passed — the nearest thing to `sfc /scannow` an app can see — plus free
storage, memory pressure, battery health and temperature, throttling,
security patch age, screen lock, encryption, USB debugging and root, in two
groups (how it's doing, security). Each comes with OK / Warning / Problem and
what to do, and it's all read again whenever you open the page. Scanning system files,
testing RAM or reading the storage chip's wear all need root on Android, so
they aren't offered rather than faked.

Design decisions and why:
[../documents/ai-knowledgebase.md](../documents/ai-knowledgebase.md).

## Installation

**Requirements:** Android 7.0 (API 24) or newer. Any architecture — there's no
native code in it.

Download `Stitches-<version>.apk` from the
[Releases page](https://github.com/Redwan-Shawkat/The-Uninstaller/releases)
and open it. Android will ask once for permission to install apps from
wherever you downloaded it; that prompt is Android's, not this app's.

It isn't on Google Play. Listing every installed package needs the
`QUERY_ALL_PACKAGES` permission, which Play restricts to a short list of
approved app categories — so the APK is the distribution channel. See the
knowledge base.

### First run

The app only scans (read-only) until you tick apps and tap **Uninstall
selected**, which always shows a confirmation first. Nothing is ticked until
you tick it; the circle above the list ticks everything shown that's safe to
pick in bulk, and clears the list when there's nothing left to add. Each removal then raises
Android's own uninstall dialog — one per app, because Android has no batch
uninstall for a normal app and no way for this app to remove anything by
itself. That dialog is the permission rail; this app never gets to skip it.

Two optional permissions, both granted from Settings and both entirely
skippable:

- **All files access** — without it the leftover scan finds nothing, because
  Android 11+ won't let an app list shared storage otherwise.
- **Usage access** — without it sizes are the app's APK size rather than its
  real footprint (code + data + cache).

The app tells you what each is for and works without either. The padlock in
the dock reopens the permission prompt; the ↻ at the top of a page looks
again.

**Preinstalled apps:** Android does not allow uninstalling one, so selecting
one opens its App Info page, where **Disable** and **Uninstall updates** are
the two things that actually exist. The app reports "Disabled" rather than
"Removed" when that's what happened, and doesn't count it toward space freed
— a disabled app is still on the partition.

## Build

```bash
./build-apk.sh          # -> dist/Stitches-<version>.apk
```

Needs a JDK 17 and an Android SDK (`local.properties` points at it, or set
`ANDROID_HOME`). The script runs the tests, builds the release APK through
Gradle with R8 shrinking on, and signs it. On first run it generates
`keystore.jks` and `keystore.properties` locally, because Android won't
install an unsigned APK — keep that file, since Android only accepts updates
signed with the same key. Neither is in git.

The result is about 85 KB. The app depends on no Android libraries at all:
no AndroidX, no Material Components, no Compose — see the knowledge base.

**No SDK set up?** Push a `v*` tag, or run **Android build** from the repo's
Actions tab: [.github/workflows/android-build.yml](../.github/workflows/android-build.yml)
builds and signs it with the repository's key and attaches it to the tagged
release.

The app icon isn't a set of PNGs: it's the Linux build's sewn `icon.svg` as
Android vector drawables. Vector drawables can't draw dashed lines, so
`tools/make_logo.py` cuts each stitch into its own short path; rerun it after
editing `icon.svg`:

```bash
python3 tools/make_logo.py   # from android/
```

## Test

```bash
./gradlew test
```

Covers the source mapping, the risk classifier, the leftover matcher, the
Home verdicts and what the select-all circle may tick, with JUnit asserts — no device and no emulator, which is the point of keeping
`Scanner.kt`'s PackageManager calls out of `Sources.kt`, `Risk.kt` and
`Leftovers.kt`.

## Safety notes

- Uninstalling always shows a confirmation listing exactly what's selected
  and its risk level; Critical items require an extra explicit checkbox
  before the Uninstall button unlocks.
- The select-all circle never ticks Critical or preinstalled items — pick
  those one at a time if you really mean it.
- Leftover files are shown with their sizes and opt-in before deletion, never
  removed silently. Your media folders (DCIM, Pictures, Music, Movies,
  Documents…) are never scanned, for the same reason the Windows build skips
  Documents.
