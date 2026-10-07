# Features

Checked before starting any work (see [CLAUDE.md](../CLAUDE.md)). Keep this
in sync with [ai-knowledgebase.md](ai-knowledgebase.md) — every entry here
that involved a design decision should have a matching note there.

## Done — Linux (`linux/`)

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
      catch stitch) inside a running-stitch border. Windows and Android
      followed in their own Stitches rounds.
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
- [x] Cleanup: in a narrow window the "Removed from" log sits under the
      table, so SIZE and the password tags stay in view.
- [x] The Linux code lives in `linux/src/stitches`, next to the `install.sh`,
      `build-deb.sh` and tests that read it from there. The release tarball
      is `linux/` itself, so `install.sh` is at its top.

### 0.2.4 — sixth round: App Manager, Web Apps, About

- [x] **App Manager** — a static catalog of 37 apps and developer tools
      (`catalog.py`, incl. qBittorrent and Spotify), each found through APT,
      Snap, Flatpak or on PATH (nvm, rustup, `~/.local/bin`…) with its
      version and how it got there; search, category, source and status
      filters; bulk install with one password per source, Flatpak and
      Flathub added first when needed; output in a Terminal panel; success
      decided by detecting again.
- [x] A Linux · Windows switch on App Manager, lit on the running OS; the
      other side is locked ("open Stitches on Windows for its apps").
- [x] **Web Apps** — PWA Builder's feature inside Stitches: paste a URL,
      name and icon fetched (or typed, picked from a file, or one of 18
      ready-made icons), duplicates with separate logins; a `.desktop` entry
      running a Chromium-family browser in app mode with its own profile.
      Open and remove (with confirmation) from the list.
- [x] **About** — after theme and update in the dock: version, what
      Stitches is, and each tool's icon with a line or two.
- [x] Dock groups: Home | Diagnose, Cleanup | App Manager, Web Apps |
      Updates, Uninstall | Drivers, Defrag | theme, update, About.
- [x] Fixed the self-update notice coming back after updating: v0.2.3
      shipped Linux as 0.2.2. Both platforms are 0.2.4, and the Linux and
      Windows release workflows fail a tag that doesn't match `__version__`.
- [x] Fixed Snap updates failing as a batch on Ubuntu when one snap is
      running ("has running apps"): `snap refresh --ignore-running`.
- [x] Defrag trims SSDs (`fstrim`) instead of skipping them; NTFS says to
      defragment it from Windows.
- [x] Diagnose's Disk health shows its `busctl` command and a line per
      drive in the Terminal.

### 0.2.4 — seventh round: App Manager tiles, PHP

- [x] App Manager shows each app's icon (bundled in `appicons/`) on tiles
      side by side, grouped by category with a select-all per category; the
      Terminal is under the tiles.
- [x] **PHP** (phase two of the setup spec): every extension of the chosen
      PHP version with a switch, Enabled / Disabled / Built in / Not
      installed, read from `/etc/php`; Apply changes previews, then runs
      phpenmod/phpdismod (and apt for missing ones) under one password,
      restarts Apache or PHP-FPM when they serve PHP, and reads back what
      took. A **Laravel** check (PHP 8.2+, Composer, the extensions)
      with a button that fixes only what's missing.
- [x] Fixed a group checkbox on Defrag (and App Manager) ticking only the
      first item.
- [x] Dock groups: … | App Manager, PHP, Web Apps | … (PHP is Linux only).

### 0.2.4 — eighth round: app details, PHP inside App Manager, web app icons

- [x] Clicking an App Manager tile opens the app's details: what it does,
      a link to its own install page, and the commands to install it by
      hand (copyable), plus an Install button. The checkbox still ticks it.
- [x] PHP is no longer a page of its own: its extensions and the Laravel
      check are in PHP's details. Dock: … | App Manager, Web Apps | ….
- [x] Web Apps: 94 site logos in groups (Social, Chat, Google, Microsoft,
      Work, AI, Developer, Watch & listen, Shopping & learning) and every
      emoji in the keyboard's groups, with a group filter and a search.
- [x] Fixed: web apps showed the browser's icon (or none) in the dock on
      Wayland; they now run through XWayland, where their own class holds.

### 0.2.4 — ninth round: Avro, WARP, Pinta

- [x] App Manager: Avro Phonetic (Bangla typing), with "After installing"
      steps in its details: add it in Settings, switch with Super+Space.
- [x] App Manager: Cloudflare WARP (the 1.1.1.1 VPN) from Cloudflare's own
      APT repository, added after a confirmation; and Pinta, a paint app.

### 0.2.5 — tenth round: MySQL and PostgreSQL users and databases

- [x] MySQL's and PostgreSQL's App Manager details: the service (state,
      Start/Restart, a picker when several PostgreSQL clusters exist), and
      the users and databases: create a user (optionally with its own
      database), change or check a password, delete a user, create a
      database for a user, delete a database (behind a tick-to-confirm).
      Passwords are never on a command line, on disk or in the Terminal.

### 0.2.6 — alongside the Windows catch-up round

- [x] A self-update check that can't reach GitHub says why, instead of
      reporting that this is the latest version; a check at startup still
      says nothing when it fails. `latest()` also catches every failure, not
      just `OSError` and `ValueError` (`http.client`'s are neither) — on
      Windows that one escaped and killed the check's thread. Version 0.2.6,
      in step with Windows.

## Planned — Linux (`linux/`)

- [ ] App Manager, next phases of the setup spec (phase three, databases,
      is done): Bangla
      typing set up by Stitches (today Avro installs and its details say
      how to add the input source; adding it, verify and repair), setup
      profiles with a preview of what will change, and an activity history.
- [ ] PHP: installing another PHP version (Ondřej's PPA), and per-SAPI
      switches (today an extension goes on or off for every SAPI at once).
- [ ] App Manager: more vendor repositories (WARP has one) and `.deb`s,
      predefined script installers (nvm,
      rustup), pnpm, and Docker's post-install step (the `docker` group).

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
- [ ] Bring the Android build the new tools where the platform allows
      (Windows has them all since its Stitches round; see below).

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
- [x] "Graphite & Signal" redesign — dark-first palette with one lime accent,
      disk-space-by-source bar that doubles as the source filter, biggest-first
      list with a shape-coded risk glyph (● ▲ ■), a Removal tray with a
      running "frees up" total, receipt-style final check. Leftovers now
      start unticked.
- [x] Row selection by clicking anywhere on a row, and Shift+click ranges
      (Critical skipped, like Select All) — the redesign's toggle column had
      been clipped off-screen at the default window size.
- [x] Fixed per-user uninstalls never finishing when the uninstaller left a
      process running (browser page, updater): output is captured to temp
      files, so only the uninstaller's own exit is waited on.
- [x] Fixed every registry (MSI/EXE) uninstall crashing before it started
      (undeclared ctypes restype in `split_command`), and an uninstall
      error now fails that item instead of freezing the window.
- [x] Fixed every machine-wide (UAC) uninstall failing: the elevated
      `cmd /c` line was mis-quoted, breaking paths under Program Files.
- [x] Installer uninstalls wait for the uninstaller's whole process tree
      (Inno/NSIS hand off to a temp copy and exit), and success is decided
      by whether the registry entry is gone, not by the exit code. Fast
      polling plus adoption of new installer temp copies (`*.tmp`, `Au_.exe`)
      covers launchers that exit before they're ever seen.
- [x] Custom app icon — `icon.ico` (16–256px) generated from the Linux
      build's `icon.svg` curves by `tools/make_icon.py`, stdlib only.
- [x] `.exe` release build — PyInstaller `--onefile --windowed`, portable,
      no Python needed on the target.
- [x] `.msi` release build — WiX; Program Files, Start Menu shortcut,
      Apps & Features entry, `MajorUpgrade`.
- [x] `windows-build.yml` — builds both on a Windows runner (they can't be
      built on the Linux dev machine), with checksums, and attaches them to
      a `v*` tag's release.

### Windows — the Stitches design and tools (0.2.0)

- [x] The Linux window: a dock along the bottom in groups (Home, the logo |
      Diagnose, Cleanup | Updates, Uninstall | Drivers, Defrag | theme,
      update), a dark action bar per page with the line loader, and round
      ticks with a select-all circle; nothing ticked at first.
- [x] Four themes (Light, Dark, AMOLED, Glass), remembered in
      `%APPDATA%\Stitches\settings.json`; first run follows Windows' own app
      mode, and the title bar goes dark with the window.
- [x] The sewn logo in `icon.ico` (`tools/make_icon.py`), also the dock's Home
      button.
- [x] Home — model, Windows, CPU, GPU, memory, uptime; BIOS/UEFI settings in
      words; memory and every drive rated Good/Warning/Critical, refreshed
      every 5 s. No temperatures (Windows gives those only to an admin).
- [x] Diagnose — ten checks behind **Scan** with a Terminal panel: drive
      health, file systems (fix: `chkdsk /scan`), free space, failed
      services (fix: start them), errors since startup, a pending restart,
      a quick memory test; Memory Diagnostic, `DISM /RestoreHealth` and
      `sfc /scannow` as fixes that say what happens first.
- [x] Cleanup — Windows Update downloads, browser caches, shader caches,
      crash dumps, error reports, Scoop's cache, temp files older than a
      day, Recycle Bin; filter, risk tag per reason, confirmation, freed total.
      In a narrow window the reason is cut short, never its risk tag.
- [x] Updates — Windows Update, winget, Chocolatey and Scoop in one list with
      search and a source filter; one permission prompt per batch source.
- [x] Drivers — display/network/audio/storage/Bluetooth/firmware devices with
      driver version, release date and what each is; Windows Update driver
      updates in one batch.
- [x] Defrag — drive tiles grouped by disk; `Optimize-Volume` defragments hard
      disks and trims SSDs, one prompt for all.
- [x] Self-update from GitHub releases: the `.msi` copy hands the new `.msi`
      to Windows Installer, the portable `.exe` swaps itself; checked first.
- [x] Version 0.2.0, in step with Linux, so the self-updater compares like
      with like.
- [x] 0.2.3: every elevated action works again (machine-wide uninstall,
      driver and Windows Update installs, Defrag, Cleanup and Diagnose
      fixes); their failures read as text, not CLIXML. The `.msi`'s Start
      Menu shortcut shows the icon. Defrag pulses while it runs (it used to
      sit at 92%), says "a few minutes", not "an hour", and reports the time
      taken. Tested on a real PC.

### Windows — 0.2.4

- [x] **App Manager** through winget: 29 apps (winget ids checked against
      `winget-pkgs`), found with one `winget export` or on PATH (the
      Store's `python.exe` stand-in doesn't count), installed one at a time
      with output in a Terminal panel, success checked by looking again.
- [x] **Web Apps**: Edge, Chrome or Brave in app mode with a profile per
      app, as a Start menu shortcut with the site's icon (a PNG-in-ICO).
- [x] **About**, the Linux · Windows switch and the same dock groups as
      Linux; Diagnose's Terminal panel is a shared widget now.
- [x] App Manager tiles with each app's icon, side by side, Terminal under
      them (`widgets.Tiles`, Table's ticking with tiles drawn instead of rows).
- [x] App Manager: Epic Games Launcher, in a new Games category.

### Windows — 0.2.6: catching up with Linux's eighth to tenth rounds

Windows was four rounds behind Linux. Design decisions in
[ai-knowledgebase.md](ai-knowledgebase.md#windows-026-catching-up-with-linuxs-eighth-to-tenth-rounds).

- [x] **App details** — clicking a tile opens the app's details: what it does,
      a link to its own Windows download page, the winget command to install
      it by hand (copyable), plus an Install button. The tick still ticks.
- [x] **"After installing"** steps in the details, for the apps that need them
      (Cloudflare WARP, Avro Keyboard, Docker Desktop's WSL 2, Rust's linker,
      MySQL's and PostgreSQL's installer questions).
- [x] App Manager tiles **grouped by category, with a select-all per
      category**, as on Linux.
- [x] **Web Apps: 94 site logos in groups** (Social, Chat, Google, Microsoft,
      Work, AI, Developer, Watch & listen, Shopping & learning) with a group
      filter and a search, replacing the 18 flat ones. No emoji: Tk 8.6
      handles non-BMP characters badly and Windows has no equivalent of the
      emoji list Linux reads out of GTK.
- [x] App Manager: **Pinta** (`Pinta.Pinta`), **Cloudflare WARP**
      (`Cloudflare.Warp`, winget's "Cloudflare One Client") and **Avro
      Keyboard** (`OmicronLab.Avro`) — 33 apps now, every id checked against
      the live winget source.
- [x] **MySQL and PostgreSQL users and databases** in their App Manager
      details, as Linux's 0.2.5: the service (state, Start/Restart, a picker
      when several PostgreSQL versions are installed), and the users and
      databases — create a user (optionally with its own database), change or
      check a password, delete a user, create a database for a user, delete a
      database (behind a tick-to-confirm). Windows has no peer or socket
      authentication, so the server's own superuser password is asked for once
      a visit; it's never on a command line, on disk or in the Terminal.
- [x] Fixed **the update check answering nothing at all**: `http.client`'s
      exceptions are not `OSError`, so one escaped `latest()` and killed the
      check's worker thread, which (unlike every page) had no error path. A
      check that can't reach GitHub now says so instead of claiming this is
      the newest, and still says nothing when it ran by itself at startup.
      Fixed on Linux too — the same hole, caught there by `run_async`.
- [x] Both platforms at 0.2.6, in step, so the self-updater compares like with
      like and can actually offer the above to a copy already on 0.2.5.

## Planned — Windows (`windows/`)

- [ ] App Manager: Maven, Composer and RustDesk, which aren't in the
      winget source (re-checked in 0.2.6: still not there).

- [ ] Count badges on the Updates and Drivers dock buttons (Linux has them).
- [ ] `sfc /verifyonly` as a real check when Stitches already runs as admin.
- [ ] Windows' own temp folder (`C:\Windows\Temp`) and Delivery Optimization's
      cache in Cleanup; both need admin rights to even measure.

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
- [x] ~~Light/dark toggle~~ — four themes since the Stitches design (below).
- [x] App icon as a vector drawable — adaptive on API 26+, plain vector
      below it. Sewn since the Stitches design, generated by
      `tools/make_logo.py`.
- [x] `.apk` release build — `build-apk.sh` runs the tests, builds through
      Gradle with R8 shrinking, and signs with a locally generated key if
      there isn't one. ~60 KB.
- [x] `android-build.yml` — tests, builds and signs on a Linux runner with
      the repository's key, with checksums, and attaches the APK to a `v*`
      tag's release.
- [x] Health check: verified-boot state, storage, memory, battery
      health and temperature, thermal throttling, security patch age, screen
      lock, encryption, USB debugging, root — each OK/Warning/Problem with
      what to do (a menu dialog, then the Home page).

### Android — the Stitches design

- [x] A dock along the bottom, as on Linux: the sewn logo is Home, then
      Uninstall, then theme and optional access. It replaces the ⋮ menu.
- [x] Home page: This phone (model, Android, build, kernel), How it's doing
      and Security, as borderless groups with an icon per heading; read again
      each time it's opened.
- [x] Uninstall page: title and subtitle, pill search and source filter, a
      card list with round ticks, the source tag after each name and the
      risk tag at the end of each reason.
- [x] Select-all circle over the list (ticked, dash, empty); never ticks
      Critical or preinstalled apps; nothing ticked at first.
- [x] A dark action bar per page with the line loader (sweeps while
      looking, fills while removing, red after a failure) and the page's
      one button.
- [x] Four themes: Light, Dark, AMOLED, Glass (the wallpaper shows
      through); first run follows the phone's light/dark setting.
- [x] The sewn logo as the launcher icon and the dock's Home button.
- [x] Dialogs in the phone's own style (rounded on current Android).

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
