# Features

Checked before starting any work (see [CLAUDE.md](../CLAUDE.md)). Keep this
in sync with [ai-knowledgebase.md](ai-knowledgebase.md) — every entry here
that involved a design decision should have a matching note there.

## Done — Linux (`src/`)

- [x] APT/dpkg backend — lists manually-installed packages (`apt-mark
      showmanual` + `dpkg-query`), tags System via Essential/Priority.
- [x] Snap backend — `snap list`, tags known base/runtime snaps as System.
- [x] Flatpak backend — `flatpak list --app`.
- [x] Wine backend — parses `system.reg`/`user.reg` Uninstall keys across
      discovered Wine prefixes.
- [x] Risk classifier (Safe / Caution / Critical) with a one-line plain-text
      reason per item.
- [x] Leftover scan — matches app name against `~/.config`, `~/.cache`,
      `~/.local/share`, `~/.var/app` after an uninstall.
- [x] GTK3 GUI: list view with source/risk tag columns, checkbox bulk select,
      search/filter, confirm-before-uninstall dialog, leftover cleanup
      dialog.
- [x] `pkexec`-based privilege escalation for apt/snap removal.
- [x] `install.sh` / `uninstall.sh` — per-user install with no pip/venv:
      copies `src/uninstaller` to `~/.local/lib`, adds a `~/.local/bin`
      launcher and an application-menu `.desktop` entry.
- [x] Fixed the window never actually rendering (blank frame — `show_all()`
      was never called after `add()`).
- [x] Scanning spinner ("Scanning for installed software…") and a per-item
      uninstall progress bar (green on success, red on failure, current
      app name shown live).
- [x] Custom app icon — nested normal/180°-rotated "A" (SVG,
      `src/uninstaller/icon.svg`), installed to the icon theme and set as
      the window icon.
- [x] Light/dark mode toggle button (native GTK `gtk-application-prefer-dark-theme`).
- [x] Fixed theme toggle being a no-op on themes with separately-named
      light/dark variants (e.g. Zorin) — now also switches `gtk-theme-name`
      by matching installed theme siblings.
- [x] Fixed the app icon not appearing in the dock/taskbar — the `.desktop`
      file is now named after the GTK application id (what Wayland actually
      matches windows against), not the binary name.
- [x] Redrew the app icon as two curved strokes (hourglass silhouette)
      instead of typed "A" glyphs — no font-rendering dependency, closer to
      the requested "glass" shape.
- [x] Uninstall/leftover-cleanup progress bar now animates a continuous
      green fill while each item is in flight (was a discrete jump only at
      completion), and leftover deletion runs through the same per-item
      animated bar instead of blocking silently on "Delete Selected".
- [x] Shortened the displayed app name to "The Uninstaller" (window title,
      dock/taskbar, app grid) — project/repo name unchanged.
- [x] Uninstall reports total disk space freed (the app's own size plus any
      leftovers actually deleted) in one summary dialog at the end of the
      flow, even when there are no leftovers to ask about.
- [x] Fixed apt uninstall never finding leftovers for a package whose own
      postrm script fails after dpkg already removed its files (exit code
      no longer the sole signal — dpkg's status field is checked too).
- [x] v0.1.0 release — MIT `LICENSE`, license metadata in `pyproject.toml`,
      real clone URL in the README, and a `git archive` source tarball as the
      GitHub release artifact.
- [x] `.deb` package — `build-deb.sh` stages a `usr/` tree and calls
      `dpkg-deb`; installs to `/usr`, declares its apt dependencies (so
      `apt install ./x.deb` pulls GTK in), and is `apt remove`-able.

### 0.2 — Stitches (briefly named SoftHUB)

- [x] Renamed to **Stitches** (it was SoftHUB for one round): package
      `stitches`, command `stitches`, app id `io.github.stitches`, `.deb`
      `stitches` (Conflicts/Replaces `softhub` and `linux-the-uninstaller`);
      `install.sh` removes copies installed under either earlier name.
- [x] `install.sh` carries a taskbar/dock pin over to the new name, in the
      same place (a rename used to unpin the app silently).
- [x] Windows and Android show Stitches too: window title, `Stitches.exe`,
      `Stitches-<v>-x64.msi` (upgrades an installed The Uninstaller in place),
      Start menu and Apps & Features name; Android's app label and
      `Stitches-<v>.apk`. Their internal ids (Windows package and
      AppUserModelID, Android applicationId) are unchanged.
- [x] Sidebar window: a dark sidebar with **Updates · Uninstall · Cleanup ·
      Drivers · Defrag**, a count badge on Updates and Drivers, and the
      Light/Dark switch; one module per page under `pages/`.
- [x] Line loader: a thin glowing line along the top of each page's action
      bar — sweeps while scanning, fills while working, red on failure.
      Replaces the spinner and the green/red progress bar.
- [x] Updates — pending updates from APT (with the repo host, so vendor
      repos like `packages.microsoft.com` show), Snap, Flatpak and
      GitHub-released AppImages; bulk update, one password prompt per
      source, per-row status.
- [x] Cleanup — APT cache, old Snap revisions, `~/.cache`, thumbnails, logs
      older than 7 days, unused Flatpak runtimes, stale temp files, Trash;
      each shows where it lives and its risk (Safe ones pre-selected until
      the fourth round), confirmation before removal, live "Removed from" log.
- [x] Drivers — detected hardware (PCI display/network/audio/storage) with
      the driver in use; updates from `ubuntu-drivers`, fwupd/LVFS and
      `linux-firmware`, bulk; update log always shown until the fifth round
      (the system spec moved to Home in the second round).
- [x] Defrag — every drive listed; ext4/btrfs/XFS on spinning disks
      defragmented (`e4defrag`, `btrfs filesystem defragment`, `xfs_fsr`);
      SSDs, unmounted drives and unsupported filesystems say why not.

### 0.2 — second round

- [x] **Home** — the spec (moved off Drivers), BIOS/UEFI settings explained in
      words (BIOS age, boot mode, Secure Boot, TPM, virtualization), live
      temperatures (hwmon + drive SMART) and fan speeds rated Good/Warning/
      Critical, memory use, and usage per partition (unmounted ones listed).
- [x] **Diagnose** — nine checks, each named after its Windows counterpart:
      system files (`dpkg --verify`, fix: reinstall the packages), package
      database, SMART disk health (UDisks2, no root), ext4 error counts (fix:
      check at next restart), free space, failed services, errors since
      startup, a no-restart memory test, and a full memtest86+ at next
      restart. Anything needing a restart asks first.
- [x] Drivers: a plain "what it is" line per device — a Linux driver, or
      firmware that applies to every OS — and the spec card moved to Home.
- [x] ~~**Update all** on Updates and Drivers~~ — removed in the fifth
      round; the select-all circle covers it.
- [x] Uninstall lists Stitches itself when `install.sh` installed it (and
      copies under its earlier names), removing exactly what `install.sh`
      placed.
- [x] Icon-only buttons with their names on hover (header refresh; the
      select all/none/safe buttons became a header checkbox in the fourth round).
- [x] Themes: Light, Dark, AMOLED, Glass — remembered across restarts.
- [x] ~~Collapsible sidebar~~ — replaced by the dock (third round).
- [x] Self-update: checks GitHub releases at start (a 10-second notice, 4 from
      the fourth round), and
      the update button installs the release matching how it was installed
      (`.deb` via apt, or the tarball's `install.sh`), verified first.
- [x] Release workflow for Linux (`linux-build.yml`); pushing a `v*` tag now
      releases all three platforms, and each uploads its own checksum file.

### 0.2 — third round

- [x] A dock of tool icons centred under the page replaces the sidebar: the
      lit icon is the open tool, names and counts show on hover, and the
      logo, theme and update buttons sit at its ends.
- [x] The theme button is icon-only; the theme list opens from it.
- [x] Logo: the same A-over-V hourglass, sewn — dashed thread strokes (a
      catch stitch) inside a running-stitch border. Linux only so far; the
      Windows `.ico` and the Android icon still draw the plain strokes.
- [x] Compact Home: three columns plus a storage strip in a smaller font,
      on one screen without scrolling at the default window size. Fans
      folded into the temperatures card; unmounted partitions on one line.

### 0.2 — fourth round

- [x] App icon shows in the taskbar right after `install.sh`: it touches the
      icon theme folder, which is what makes GNOME Shell rescan it.
- [x] Logo stitches actually read as stitches at dock size: square-ended
      9-on/6-off thread over a faint seam line, a stitch on each tip.
- [x] Dock groups: Icon | Home | Diagnose, Cleanup | Updates, Uninstall |
      Drivers, Defrag | theme, update (the logo became Home in the fifth).
- [x] Window and dock themes picked separately (Light/Dark/AMOLED/Glass
      each), so any mix works; older settings keep their look.
- [x] Home cards are only as tall as their content, with narrower gaps.
- [x] Diagnose output panel: each command and what it prints, live, fixes
      included.
- [x] A select-all circle in the ticks' column header replaces the select
      buttons (Updates, Uninstall, Cleanup, Drivers; per OS group on
      Defrag); nothing is ticked when a page opens.
- [x] Cleanup explains what it removes and what it never touches (your
      files, installed apps), with each location's meaning in its own column
      (a card until the fifth round, now one line in the action bar).
- [x] Drivers: a Released column (the maker's release date), and the source
      as a clickable icon.
- [x] Defrag: partitions as tiles, grouped by OS (Linux, Windows, macOS,
      Boot, Other).
- [x] Update notice: 4 seconds, with a line running down as it goes.

### 0.2 — fifth round

- [x] The dock logo is the Home button; no separate Home icon.
- [x] Home: borderless groups, each titled with an icon.
- [x] Diagnose's output panel is titled Terminal.
- [x] Cleanup: the explanation card is one line in the action bar, the risk
      tag ends each reason (no Risk column), and a filter (Safe, Caution, No
      password needed).
- [x] No Update all on Updates or Drivers; Update selected is the one button.
- [x] New icons: Uninstall is an app grid with one taken out (was a trash
      can), Drivers a chip, Diagnose a screen with a magnifier (was a
      shield), Cleanup a brush (was a crossed circle); bundled in `icons/`,
      with stand-ins for themes that lack them.
- [x] Drivers: the Update log card is gone; failed updates open a dialog.
- [x] Defrag: one card per OS group, tiles side by side inside it.

## Planned — Linux (`src/`)

- [ ] Fan sensors on boards whose sensor chip driver isn't loaded
      (`nct6775`, `it87`): detect the chip and offer to load the module.
- [ ] A SMART self-test button (UDisks2 can start one; it needs a polkit
      prompt and a way to show its progress).
- [ ] File-system checks for btrfs (`btrfs scrub`) and XFS; today only ext4
      error counts are read.

- [ ] Refresh the APT index from Updates (`apt update`). Today the list is
      as fresh as the system's own daily refresh; doing it here costs a
      password prompt per check.
- [ ] Download size for APT updates (one `apt-cache show` call would do it).
- [ ] One password prompt for all admin Cleanup locations together (today
      it's one per location: APT cache, Snap revisions, logs).
- [ ] Fragmentation analysis before defrag. Needs root: `e4defrag -c` run
      unprivileged prints nothing.
- [ ] AppImage update formats beyond `gh-releases-zsync` (plain zsync URLs,
      GitLab, `latest-pre`), and AppImages outside the usual folders.
- [ ] Bring the Windows and Android builds the new tools where the platform
      allows (the design canvas that sketched them has been deleted).

- [ ] Reverse-dependency check for apt packages (currently heuristic-only,
      see ai-knowledgebase.md "Risk heuristic, not a dependency graph").
- [ ] Package-manager-owned leftovers under `/etc` (needs root; currently
      only user-home leftovers are offered).
- [ ] RPM/Fedora backend.
- [ ] Flatpak release package (the `.deb` landed in v0.1.0; a Flatpak would
      additionally cover non-Debian distros).

## Done — Windows (`windows/`)

The Windows build: same architecture, same feature set, platform-specific
leaves. Design decisions in
[ai-knowledgebase.md](ai-knowledgebase.md#windows-port-windows).

- [x] Registry backend — MSI/EXE installers from all three Uninstall views
      (64-bit, `WOW6432Node`, `HKCU`) via stdlib `winreg`; filters patches,
      surfaces the `SystemComponent` entries Apps & Features hides.
- [x] Microsoft Store backend — `Get-AppxPackage` as CSV.
- [x] Chocolatey backend — reads `$ChocolateyInstall\lib\*\*.nuspec` off
      disk rather than calling `choco list`.
- [x] Scoop backend — reads `$SCOOP\apps\*\current\manifest.json`; covers
      the user and global roots.
- [x] Risk classifier (Safe / Caution / Critical) off registry fields and
      Appx `IsFramework`, with a one-line plain-text reason per item.
- [x] Leftover scan — matches app name against `AppData\Roaming`,
      `AppData\Local`, `AppData\LocalLow` and `ProgramData` after an
      uninstall.
- [x] UAC privilege escalation (`ShellExecuteEx` + `runas`) for machine-wide
      removals, per-item: per-user installs raise no prompt. Captures the
      elevated process's output and exit code, which plain `ShellExecute`
      can't.
- [x] tkinter/ttk GUI: list view with source/risk tag columns, checkbox bulk
      select, search/filter, risk-reason tooltips, confirm-before-uninstall
      dialog, leftover cleanup dialog, scan progress and per-item uninstall
      progress bar (green on success, red on failure).
- [x] Light/dark mode toggle (two `clam` palettes — ttk's native theme
      ignores configured colours).
- [x] Correct taskbar icon via an explicit AppUserModelID, and DPI awareness
      so the UI isn't a blurry upscale.
- [x] Custom app icon — `icon.ico` (16–256px) generated from the Linux
      build's `icon.svg` curves by `tools/make_icon.py`, stdlib only.
- [x] `.exe` release build — PyInstaller `--onefile --windowed`, portable,
      no Python needed on the target.
- [x] `.msi` release build — WiX; Program Files, Start Menu shortcut,
      Apps & Features entry, `MajorUpgrade`.
- [x] `windows-build.yml` — builds both on a Windows runner (they can't be
      built on the Linux dev machine), with checksums, and attaches them to
      a `v*` tag's release.

## Planned — Windows (`windows/`)

- [ ] Registry leftovers (orphaned `HKCU\Software\<Vendor>` keys). Needs its
      own confirmation UI before it ships — a wrongly deleted key has no
      Recycle Bin, so it can't just join the existing file list.
- [ ] Size for Store/Chocolatey/Scoop items (only the registry reports one
      today; the rest would need a directory walk per package).
- [ ] Per-app install-directory leftovers under `Program Files` (needs
      elevation, like the Linux build's `/etc` case).
- [ ] Code signing for the `.exe` and `.msi` — unsigned builds raise a
      SmartScreen warning on first run. Needs a certificate, not code.

## Done — Android (`android/`)

The Android build: same architecture, same feature set, platform-specific
leaves. Design decisions in
[ai-knowledgebase.md](ai-knowledgebase.md#android-port-android).

- [x] PackageManager backend — every installed package, with the installer
      that put it there; one scan, not one query per source, because Android
      keeps a single register.
- [x] Source tags from the recorded installing package — Play Store,
      F-Droid, other app store (named), sideloaded APK, preinstalled.
- [x] Risk classifier (Safe / Caution / Critical) with a one-line plain-text
      reason per item. Three signals are authoritative rather than guessed:
      the default launcher, active device admins, and the active keyboard.
- [x] Real app sizes via `StorageStatsManager` when usage access is granted,
      falling back to the APK's own size when it isn't.
- [x] Leftover scan — matches app name, package name and the package's last
      segment against shared storage, `Download`, `Android/data` and
      `Android/obb`; the user's media folders are never scanned.
- [x] Removal through the system's own uninstall dialog, one app at a time,
      with the result read back from the package manager rather than from
      the activity result code.
- [x] Preinstalled apps open App Info instead, where Disable and Uninstall
      updates live; a disable is reported as such and isn't counted as space
      freed.
- [x] Platform-widget GUI (no AndroidX, no Material Components, no Compose):
      list with source/risk/size per row, checkbox bulk select, search,
      source filter, confirm-before-uninstall dialog with a Critical
      acknowledgement, leftover cleanup dialog, scan and removal progress.
- [x] Light/dark toggle (two platform Material themes, one risk palette that
      reads on both).
- [x] App icon as a vector drawable carrying the Linux build's `icon.svg`
      path data verbatim — adaptive on API 26+, plain vector below it. No
      rasteriser, no generator script, no committed bitmaps.
- [x] `.apk` release build — `build-apk.sh` runs the tests, builds through
      Gradle with R8 shrinking, and signs with a locally generated key if
      there isn't one. ~60 KB.
- [x] `android-build.yml` — tests, builds and signs on a Linux runner with
      the repository's key, with checksums, and attaches the APK to a `v*`
      tag's release.
- [x] Health check (menu): verified-boot state, storage, memory, battery
      health and temperature, thermal throttling, security patch age, screen
      lock, encryption, USB debugging, root — each OK/Warning/Problem with
      what to do.

## Planned — Android (`android/`)

- [ ] Split the leftover scan by confidence. A folder named exactly after the
      package is certain; a fuzzy name match on a top-level folder is a
      guess, and the dialog currently pre-checks both alike.
- [ ] Cache-only cleanup for apps you're keeping (`StorageStats` already
      reports cache bytes per app; clearing it needs no uninstall).
- [ ] Batch removal without a dialog per app. Only a device owner or a
      privileged app can do this, so it needs a `dpm set-device-owner` or
      Shizuku path — a different trust model, not a code change.
- [ ] Play-flavoured build. Needs `QUERY_ALL_PACKAGES` approval or a
      declared `<queries>` list, which would cut the app list down to
      whatever was declared ahead of time.

## Out of scope (v0.1)

- Updates for a `.deb` downloaded from a vendor's website with no apt repo
  behind it — there's no update feed to ask. Vendors with a repo
  (VS Code, Chrome, Brave…) are covered through APT.
- Bare executables installed with no package manager involvement at all
  (nothing to detect them by) — on Windows, that also covers portable
  apps unzipped into a folder, and `winget`, which is not a separate
  source at all (see ai-knowledgebase.md).
- Rooted-device operations on Android (`pm uninstall --user 0`, removing a
  system app outright). Android's own limits are the safety model this app
  works inside, not an obstacle to route around.
- Auto-update / telemetry / background scanning daemon.
