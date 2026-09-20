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

## Planned — Linux (`src/`)

- [ ] Reverse-dependency check for apt packages (currently heuristic-only,
      see ai-knowledgebase.md "Risk heuristic, not a dependency graph").
- [ ] Package-manager-owned leftovers under `/etc` (needs root; currently
      only user-home leftovers are offered).
- [ ] RPM/Fedora backend.
- [ ] Real `.deb`/Flatpak release package (`install.sh` gets it running, but
      it isn't a versioned, `apt remove`-able package).

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

## Out of scope (v0.1)

- Bare executables installed with no package manager involvement at all
  (nothing to detect them by) — on Windows, that also covers portable
  apps unzipped into a folder, and `winget`, which is not a separate
  source at all (see ai-knowledgebase.md).
- Auto-update / telemetry / background scanning daemon.
