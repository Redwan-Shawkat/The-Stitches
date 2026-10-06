# Stitches

Windows has Revo, IObit, Geek Uninstaller — a whole category of tools that
find installed software no matter how it got there, and scrub the leftovers
behind it. Ubuntu/Debian-based Linux doesn't: the built-in app store only
manages what it installed itself. Anything you `apt install`ed, grabbed as a
`.deb` from a browser, added via Snap or Flatpak outside the store UI, or
run through Wine is invisible to it.

Stitches is one window for all of it, with nine tools in a dock along the bottom:

| Tool | What it does |
|---|---|
| **Home** | What the PC is (OS, CPU, GPU, memory, board, disks), its BIOS/UEFI settings explained in words (Secure Boot, TPM, virtualization, boot mode, BIOS age), live temperatures and fan speeds rated Good/Warning/Critical, memory use, and how full every partition is. |
| **Diagnose** | Linux's answers to Windows' repair tools, in one scan: system files against their packages (`sfc /scannow`), the package database (`DISM`), file-system errors (`chkdsk`), SMART disk health, a memory test that needs no restart, failed services, and errors logged since startup — with a fix button where one exists, and a terminal panel showing each command and what it prints as it runs. Fixes that need a restart (a full file-system check, memtest86+) say so and ask first. |
| **App Manager** | A built-in catalog of the apps and developer tools people set a PC up with — VS Code, Android Studio, Docker, Git, Node.js, Go, Rust, PHP, Python, Java, MySQL, PostgreSQL, Brave, LibreOffice, VLC, Spotify, Kooha, Pinta, qBittorrent, LocalSend, AnyDesk, Cloudflare WARP (1.1.1.1), Avro Phonetic, Wine and more (Epic Games on Windows) — as tiles with each app's icon, showing what's installed, at what version and through what (APT, Snap, Flatpak, or found on PATH, like an nvm Node). Click an app for what it does, a link to its own install page, and the terminal commands to install it by hand; Avro's and WARP's also say how to turn them on after installing. WARP comes from Cloudflare's own repository, which Stitches adds after asking. PHP's details also hold every extension of your PHP (from Ubuntu's packages) with an on/off switch, and a Laravel check (PHP 8.2+, Composer, bcmath, mbstring, pdo_mysql and the rest) with one button that turns on or installs only what's missing; nothing runs until you apply, you see the list of changes first, type your password once, and Apache or PHP-FPM is restarted for you if it serves PHP (Linux only). MySQL's and PostgreSQL's details show the server (Start, Restart) and its users and databases: create a user (with its own database if you like), change or check a password, delete a user, create or delete a database. Each change asks for your password once and the lists are read again to show it took; database passwords are never put on a command line, saved, or shown in the terminal panel (Linux only). Tick any number and install them through APT, Snap or Flatpak (Flathub is added if it's missing), one password per source, with each command and its output in a terminal panel. The catalog is fixed in the source: nothing typed is ever run. A Linux · Windows switch shows which OS's apps it manages. |
| **Web Apps** | Any website as an app of its own: paste the address and its name and icon are filled in (or pick a ready-made one: about 90 site logos and every emoji, in groups as on a phone keyboard, with a search). It gets its own menu entry, window, dock icon and login — add Facebook twice for two accounts. Runs in Chrome, Chromium, Brave, Edge or Vivaldi's app mode; nothing is compiled. |
| **Updates** | Pending updates from APT (including vendor repos like `packages.microsoft.com`), Snap, Flatpak, and AppImages published on GitHub — tick the ones you want, or the circle at the top for all of them. |
| **Uninstall** | Every installed app, tagged by how it got onto your system and rated Safe/Caution/Critical to remove, with bulk uninstall and leftover-file cleanup. That includes Stitches itself when `install.sh` put it in your home folder. |
| **Cleanup** | APT's package cache, old Snap revisions, app caches, thumbnails, week-old logs, unused Flatpak runtimes, stale temp files and the Trash — each showing where it lives, what removing it means and how risky that is, filterable by risk, with a live log of what was removed from where. Your files and installed apps are never touched; the Trash (files you already deleted) is the one exception, and it says so. |
| **Drivers** | The hardware in the machine, what each device runs on, and in plain words what each item is — a Linux driver, or firmware that runs inside the device and applies to every OS. Proprietary drivers (`ubuntu-drivers`), device firmware (fwupd/LVFS) and `linux-firmware` update in bulk. Each shows when its maker released it; the source is an icon that says what it is when clicked. |
| **Defrag** | Every partition as a tile, grouped by the OS it belongs to (Linux, Windows, boot…); ext4, btrfs and XFS on hard disks get defragmented, and SSDs get a TRIM (`fstrim`) instead, as Windows' Optimize does. NTFS drives say to defragment them from Windows. |

Each tool is an icon in the dock, with its name on hover, grouped: Home
(the logo) · Diagnose, Cleanup · App Manager, Web Apps · Updates, Uninstall ·
Drivers, Defrag, then theme, update and **About** (the version, and a line
and a picture for each tool). The window and the
dock each take one of four themes — Light, Dark, AMOLED (pure black) and
Glass (see-through) — in any mix, say a dark window with a white dock.
Stitches checks GitHub for a newer release when it starts; the notice runs a
line down and goes away by itself after 4 seconds, and the update button at
the end of the dock installs it.

![Main window mockup](screenshots/main-window-mockup.png)
*(Hand-drawn mockup of the 0.1 layout, before the dock — see
[Screenshots](#screenshots) below.)*

## What Uninstall detects

| Tag | What it means |
|---|---|
| **Terminal / .deb** | Installed with `apt install` or a downloaded `.deb` (`dpkg -i`). |
| **Snap Store** | Installed as a Snap. |
| **Flatpak** | Installed as a Flatpak. |
| **Wine (Windows app)** | A Windows program installed into a Wine prefix. |
| **Local install** | Stitches itself, when `install.sh` put it in your home folder (no package manager knows about that copy). |

Each item is also rated:

- 🟢 **Safe** — a standalone app; removing it only removes that app.
- 🟡 **Caution** — other apps or your desktop may depend on this; read the
  reason shown before removing.
- 🔴 **Critical** — a core OS/desktop component (tagged **System**); never
  ticked by the select-all circle.

Full requirements: [documents/SRS.md](documents/SRS.md). Design decisions
and why: [documents/ai-knowledgebase.md](documents/ai-knowledgebase.md).

The Linux build lives in [linux/](linux/); everything below is about it.

**On Windows?** Apps & Features has the same blind spots — it can't see
Microsoft Store apps in the same list, and it can't see Chocolatey or Scoop
at all. The Windows build lives in [windows/](windows/) and ships as an
`.exe` and an `.msi`. It has the same dock and tools (PHP's extensions are Linux only), built on
Windows' own: Windows Update, winget, `chkdsk`, `sfc`, `DISM` and
`Optimize-Volume`.

**On Android?** Settings lists your apps but never says where any of them
came from, removes them one at a time, and leaves behind whatever an app
wrote to your storage. The Android build lives in [android/](android/) and
ships as an `.apk`. It looks like the Linux build (a dock with the sewn logo
as Home, dark action bars, round ticks, Light/Dark/AMOLED/Glass), and its
Home page is a health check (verified boot, storage, battery, temperature,
security patch age, screen lock, USB debugging, root).

## Installation

**Requirements:** Ubuntu or another Debian-based Linux distribution with a
GTK3 desktop.

### Option A — install the `.deb` (recommended)

Download `stitches_<version>_all.deb` from the
[Releases page](https://github.com/Redwan-Shawkat/The-Uninstaller/releases),
then:

```bash
sudo apt install ./stitches_0.2.0_all.deb
```

`apt` pulls in `python3-gi`/`gir1.2-gtk-3.0` itself if they're missing. This
installs system-wide (`/usr/bin`, `/usr/lib`), adds **Stitches** to
your application menu, and — fittingly — uninstalls cleanly:

```bash
sudo apt remove stitches
```

### Option B — per-user install, no root

Installs into your home directory only. Needs `git` if you clone.

1. **Get the code** — either clone it:
   ```bash
   git clone https://github.com/Redwan-Shawkat/The-Uninstaller.git
   cd The-Uninstaller/linux
   ```
   or download `stitches-<version>.tar.gz` from the
   [Releases page](https://github.com/Redwan-Shawkat/The-Uninstaller/releases)
   and unpack it:
   ```bash
   tar -xzf stitches-*.tar.gz
   cd stitches-*
   ```
2. **Run the installer**
   ```bash
   ./install.sh
   ```
   This installs `python3-gi`/`gir1.2-gtk-3.0` via `apt` only if they're
   missing (a stock Ubuntu desktop already has them — no pip, no venv, see
   [ai-knowledgebase.md](documents/ai-knowledgebase.md#stack-choice) for
   why), copies the app to `~/.local/lib/stitches`, and adds:
   - a `stitches` command in `~/.local/bin`
   - an entry in your application menu (**Stitches**)
3. **Open a new terminal** (only needed the first time, so `~/.local/bin`
   is on `PATH`) and run:
   ```bash
   stitches
   ```
   — or launch it from your application menu instead.

Re-run `./install.sh` any time after a `git pull` (or after unpacking a
newer release tarball) to update. It also replaces a copy installed under the
app's earlier names (SoftHUB, The Uninstaller) and keeps its taskbar pin. To
remove everything it placed: `./uninstall.sh`.

Pick one of A or B, not both: the `~/.local/bin` launcher from Option B
comes earlier on `PATH` than the packaged `/usr/bin` one, so a stale per-user
copy would quietly win over the `.deb`.

**Don't want to install anything?** Run it straight from the checkout's
`linux/` folder:
```bash
PYTHONPATH=src python3 -m stitches
```

### First run

Every page scans (read-only) as soon as the window opens, and nothing
changes until you tick items (nothing starts ticked; the circle at the top
of the ticks selects them all) and press the button in the dark bar at the
bottom. Uninstall and Cleanup always show a confirmation first. Anything
that touches system packages, firmware, logs or drives prompts for your
password via the desktop's normal authorization dialog (`pkexec`) — this
app never asks for a password itself. APT and Snap updates go as one batch
each, so a bulk update asks once per source, not once per package.

While a page works, a thin line runs along the top of its bar: sweeping
back and forth while scanning, filling up while updating, removing or
defragmenting, and turning red if something fails. Other pages stay
usable in the meantime. The last two buttons in the dock pick the window
and dock themes (remembered in `~/.config/stitches/settings.json`) and
update Stitches itself. Diagnose waits for you to press **Scan**, because checking
every installed file takes a minute or two.

## Build

Each platform builds with one script. None of them needs anything beyond that
platform's usual toolchain.

### Linux — `.deb` and source tarball

On any Debian/Ubuntu machine:

```bash
./build-deb.sh                     # -> dist/stitches_<version>_all.deb
VERSION=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml)
git -C .. archive --format=tar.gz --prefix=stitches-$VERSION/ --add-file=LICENSE --add-file=README.md \
  -o linux/dist/stitches-$VERSION.tar.gz HEAD:linux   # -> dist/stitches-<version>.tar.gz
```

`build-deb.sh` reads the version from `pyproject.toml`, stages a tree under
`dist/deb/` and hands it to `dpkg-deb` — no debhelper, no maintainer scripts
(dpkg's own triggers refresh the desktop and icon caches). The tarball is the
tree `install.sh` installs from. A release needs **both**: Stitches' update
button installs the `.deb` on a system install and the tarball on a per-user
one.

### Windows — `.exe` and `.msi`

On Windows with Python 3.10+ and the .NET SDK, from `windows\`:

```powershell
.\build-all.ps1        # -> dist\Stitches.exe, dist\Stitches-<version>-x64.msi
```

PyInstaller and WiX are fetched by the script if missing. There's no way to
build these on Linux (see [windows/README.md](windows/README.md)); the CI
workflow below builds them on a Windows runner.

### Android — signed `.apk`

With JDK 17 and an Android SDK (`android/local.properties` points at it, or set
`ANDROID_HOME`), from `android/`:

```bash
./build-apk.sh          # -> dist/Stitches-<version>.apk
```

It runs the tests, builds with R8 and signs the APK. The first run generates
`android/keystore.jks` + `keystore.properties`; **keep them**, because Android
only accepts an update signed with the same key. Neither is in git.

## Releasing on GitHub

Pushing a version tag is the whole release. Three workflows start on any
`v*` tag, build Linux, Windows and Android in parallel, and attach everything
to one GitHub release — whichever finishes first creates it:

| Workflow | Attaches |
|---|---|
| `linux-build.yml` | `stitches_<v>_all.deb`, `stitches-<v>.tar.gz`, `SHA256SUMS-linux.txt` |
| `windows-build.yml` | `Stitches.exe`, `Stitches-<v>-x64.msi`, `SHA256SUMS-windows.txt` |
| `android-build.yml` | `Stitches-<v>.apk`, `SHA256SUMS-android.txt` |

**Once, before the first Android release:** the workflow signs with the
repository's key, so give it yours (Settings › Secrets and variables ›
Actions, or with the GitHub CLI):

```bash
sudo apt install gh && gh auth login     # once
base64 -w0 android/keystore.jks | gh secret set ANDROID_KEYSTORE_B64
grep storePassword android/keystore.properties | cut -d= -f2- | gh secret set ANDROID_KEYSTORE_PASSWORD
grep keyAlias      android/keystore.properties | cut -d= -f2- | gh secret set ANDROID_KEY_ALIAS
grep keyPassword   android/keystore.properties | cut -d= -f2- | gh secret set ANDROID_KEY_PASSWORD
```

**Every release:**

1. Bump the version where it changed: `pyproject.toml` and
   `linux/src/stitches/__init__.py` (Linux), `windows/pyproject.toml` (Windows),
   `versionName`/`versionCode` in `android/app/build.gradle.kts` (Android).
2. Commit and push to `master`.
3. Tag and push the tag:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
4. Watch it build: the repository's **Actions** tab, or `gh run watch`.
   A few minutes later everything is on
   `https://github.com/Redwan-Shawkat/The-Uninstaller/releases/latest`, and
   every running Stitches sees the new version the next time it starts.

To edit the notes afterwards: `gh release edit v0.2.0 --notes-file NOTES.md`.
A build that failed can be re-run from the Actions tab; the upload replaces
what's there (`--clobber`).

## Test

```bash
python3 tests/test_core.py     # or: pytest tests/
```

Covers every parser (dpkg, apt, snap, flatpak, the Wine registry, lspci,
ubuntu-drivers, fwupd, lsblk, UDisks2, `dpkg --verify`, journald, /proc, an
AppImage's ELF header), the temperature and health verdicts, the job
planners, the self-update choices and the risk classifier with plain asserts
— no live system state required. The Android tests: `cd android && ./gradlew test`.

## Screenshots

The image above is a mockup, not a live screenshot: this repo was put
together in a sandboxed environment where GNOME's screenshot D-Bus API
(`org.gnome.Shell.Screenshot`) refuses non-interactive callers, and the
`xdg-desktop-portal` equivalent needs a human to click through it. Run the
app on your own desktop and drop a real screenshot in `linux/screenshots/` —
happy to update this README to reference it.

## Safety notes

- Uninstalling always shows a confirmation listing exactly what's selected
  and its risk level; Critical/System items require an extra explicit
  checkbox before the Uninstall button unlocks.
- The select-all circle never selects Critical/System items — pick those one
  at a time if you really mean it.
- Leftover files are shown and opt-in before deletion, never removed
  silently.
- Nothing starts ticked, on any page. In Cleanup the Trash and temp files
  are rated Caution. Temp files are only ever your own, a day old, and not
  holding a socket (so a running ssh-agent or tmux is left alone).
- An AppImage update — and Stitches' own update — is downloaded first and
  only installed once its size, and GitHub's checksum when it publishes one,
  match.
- Diagnose only reads. A fix runs when you press it; one that needs a
  restart (a full file-system check, the memory test) explains what will
  happen and asks before it sets anything, then asks again before
  restarting.
- App Manager only runs the install commands written into its catalog; no
  text box, URL or file can add a command. Whether an install worked is
  decided by asking the package manager afterwards, not by the exit code.
- Removing a web app asks first, since its login goes with it, and only
  ever deletes the folder Stitches made for that app.

## License

[MIT](LICENSE) — © 2026 Redwan Shawkat.
