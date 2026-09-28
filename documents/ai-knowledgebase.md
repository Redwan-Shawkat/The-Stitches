# AI Knowledge Base

Design decisions and why, so future work doesn't re-litigate them. Checked
before starting any work (see [CLAUDE.md](../CLAUDE.md)); updated alongside
[features.md](features.md) whenever a feature lands.

## Stack choice

**Python 3 + PyGObject (GTK3)**, no pip dependencies. Ubuntu desktop ships
Python 3 and GTK3's Python bindings as part of the base OS (GNOME Software,
Update Manager etc. are themselves GTK apps) — so this adds *zero* new
system packages on the target platform, per ponytail rung 4/5 (native
platform feature / already-installed dependency beats a new one). Electron
or Qt would both work but either pull in a runtime the OS doesn't already
have.

## Why `apt-mark showmanual`, not the full dpkg package list

`dpkg-query -l` lists 1000+ packages on a typical desktop, nearly all of
them dependencies nobody chose. `apt-mark showmanual` is exactly apt's own
definition of "the user asked for this" — it's what `apt autoremove`
protects. Crucially it also lists packages installed by `dpkg -i some.deb`
(a downloaded .deb), which is one of the sources this project exists to
surface. Enriched per-package with one `dpkg-query -W -f=...` call for
version/size/priority/essential fields.

## Risk heuristic, not a dependency graph

Real risk assessment would mean walking full reverse-dependency graphs
(`apt-cache rdepends`) per package — correct, but one subprocess per
package makes the initial scan slow (FR: "a few seconds"). Instead risk is
read straight off fields the single `dpkg-query` call already returns:
`Essential: yes` or `Priority: required` → Critical, `Priority: important`
→ Caution, everything else → Safe. Snap/Flatpak apps are Safe unless they
match a known runtime-base name pattern (`core*`, `snapd`,
`gtk-common-themes`, `*-platform`, `*.Platform`/`*.Sdk`) → Critical/System.
Wine apps are always Safe (they live entirely inside a user's prefix; wine
runtimes like `wine-mono`/`wine-gecko` installers are a rare edge case, not
handled).

`# ponytail:` marks this in `risk.py` — upgrade path is a real
`apt-cache rdepends` pass, gated behind a "deep scan" button, if users hit a
case where the heuristic is wrong.

## Privilege escalation: `pkexec`, not `sudo`

Removing an apt or snap package needs root. `sudo` needs a terminal;
`pkexec` is the standard PolicyKit GUI prompt every Ubuntu desktop already
has (it's what GNOME Software itself uses under the hood) — no new
dependency, no password ever touches this app's process. Flatpak
`--user` installs and Wine (fully unprivileged, lives under `$HOME`) never
need it.

## Wine detection: parse the prefix's own registry files directly

Wine has no central database of installed Windows apps — each prefix
(`~/.wine` by default, or any `WINEPREFIX`) keeps its own `system.reg` /
`user.reg`, plain-text exports of the Windows registry. An app with a real
installer registers an `Uninstall\<Key>` subkey there (`DisplayName`,
`UninstallString`, `EstimatedSize`) — the same place Wine's own bundled
`wine uninstaller` GUI reads from. We parse that text format directly with
a small regex (`backends/wine_backend.py: parse_uninstall_keys`) instead of
shelling out to `wine uninstaller --list`, because the file is already
plain text and parsing it is faster and doesn't require spinning up a Wine
process just to list apps. Prefixes are discovered by checking
`~/.wine`, `~/.local/share/wineprefixes/*`, and `~/.PlayOnLinux/wineprefix/*`
(the common locations); Bottles/Lutris keep prefixes elsewhere and aren't
scanned yet — see features.md.

## Leftover scan is name-matching, not a package-manager feature

`apt purge` (used instead of `remove`) already cleans `/etc` config apt
knows about. What it *can't* know about is a `~/.config/<app>` directory
the app created itself at runtime. There's no manifest for that, so the
scan is a heuristic: after uninstall, glob `~/.config`, `~/.cache`,
`~/.local/share`, `~/.var/app` for entries whose name matches the removed
app's name/id (case-insensitive substring). False negatives (oddly-named
dirs) are possible; false positives are avoided by always showing the list
and asking before deleting anything (FR5) rather than deleting silently.

## Pure logic vs. subprocess boundary

Every backend splits into a `scan()`/`uninstall()` pair that shells out, and
a pure `parse_*`/`classify_*` function that takes text/data in and returns
structured results — so `tests/` can cover the parsing and risk logic
without needing dpkg/snap/flatpak/wine actually installed or a live system
state to fixture against.

## Installer: a copy + launcher script, not pip/venv

`pyproject.toml` still exists (so `pip install -e .` works for anyone who
wants it), but the documented, supported install path is `install.sh`. Why
not the venv from the earlier README draft: a venv needs
`--system-site-packages` to see the system's GTK3 bindings, needs
activating (or a wrapper that activates it, which is what a launcher script
does anyway), and buys nothing since this project has zero pip
dependencies to isolate. There *is* a `.deb` as of v0.1.0 (see
[Packaging](#packaging-a-staged-tree-and-dpkg-deb)) and it's the
recommended install for most people, but `install.sh` stays: it's the only
path that needs no root at all, and it's what a contributor working from a
checkout actually runs. `install.sh` does the minimum that
makes "install it" actually mean something: copies the package to
`~/.local/lib`, drops a launcher in `~/.local/bin` (already the recommended
per-user bin dir on Ubuntu), and writes a `.desktop` file so it's a real
app-menu entry, not just a script you remember to run. `uninstall.sh` is
the exact inverse — three `rm`s, no state left behind to manually clean up
later, which is exactly the kind of thing this project exists to prevent
in *other* software.

## GUI fixes: `show_all()`, scan/uninstall progress, icon, theme toggle

**The blank-window bug**: the window looked "stuck loading" but was never
scanning-slow — `self.add(self._build_ui())` was never followed by
`self.show_all()`. In GTK3 a widget's `visible` property has to become True
through `show()`/`show_all()` on the toplevel; `present()` only maps the
window itself, not its children. Root-caused once (call added in
`__init__`) rather than patched per-symptom.

**Progress feedback**: a `Gtk.Spinner` + status label covers scanning
("Scanning for installed software…"); uninstalling reuses one
`Gtk.ProgressBar` updated per item from the worker thread via
`GLib.idle_add` (never touch GTK widgets off the main thread) — fraction
advances per app, CSS class `op-success`/`op-error` recolors the fill
green/red per the last completed item, and the status label names the app
currently being removed. One bar reused for both phases; a second bar or a
per-row indicator would be scaffolding for a v0.1 with usually a handful of
selected items.

**App icon**: hand-written SVG (`src/uninstaller/icon.svg`) — a normal "A"
stacked on its own 180°-rotated copy, tips meeting like an hourglass. Plain
XML, no icon-editor or Pillow dependency (ponytail rung 3: stdlib/text
suffices). `install.sh` drops a copy into
`~/.local/share/icons/hicolor/scalable/apps/` (the standard per-user XDG
icon path) so both the `.desktop` entry and `Gtk.Window.set_icon_from_file`
pick it up; `uninstall.sh` removes it symmetrically.

**Light/dark toggle**: a `Gtk.ToggleButton` flips
`Gtk.Settings:gtk-application-prefer-dark-theme` — the same switch GNOME's
own dark-mode setting flips, so every existing widget already reacts
correctly with zero theme-specific styling of our own. Session-only (not
persisted to a config file yet); add a small JSON under
`~/.config/linux-the-uninstaller/` if users ask for it to stick across
restarts.

`Gdk` needed its own `gi.require_version("Gdk", "3.0")` before import —
without it, whichever other GTK4 app ran first in the session (or a
default-version probe) can leave namespace resolution pointing at GTK4's
`Gdk`, and mixing Gdk3/Gtk3 fails at import.

## Follow-up: theme toggle had no effect, icon didn't show

Both traced back to real system testing (Zorin OS, theme `ZorinPurple-Dark`,
GNOME/Mutter on Wayland) rather than assumptions:

- **Theme toggle**: `gtk-application-prefer-dark-theme` only does anything
  for themes that ship a single base name plus an automatic "-dark"
  variant (Adwaita, Yaru). Many themes — Zorin's included — ship the
  light/dark pair as two unrelated theme names (`ZorinPurple-Light` /
  `ZorinPurple-Dark`) that this property doesn't touch at all, so the
  button visibly did nothing. Fixed by also scanning the installed theme
  directories (`/usr/share/themes`, `~/.themes`, `~/.local/share/themes`),
  stripping the light/dark suffix to find the sibling theme name, and
  setting `gtk-theme-name` directly (`_find_theme_variant` in gui.py) —
  covers both naming schemes generically instead of hardcoding either
  distro's convention. The boolean property is still set too, for themes
  that do use it.
- **App icon**: GTK's Wayland backend tags every top-level window with the
  `Gtk.Application`'s `application-id` (`io.github.linux-the-uninstaller`),
  not the process name — so the shell only shows a custom taskbar/dock icon
  when a `.desktop` file of that *same* id exists. The file was named
  `linux-the-uninstaller.desktop`, a mismatch, so it silently fell back to
  a generic icon. Fixed by naming the installed `.desktop` file and its
  icon after the application id instead of the human-readable binary name;
  `install.sh` also does a one-time cleanup of the old, wrongly-named
  files from earlier installs. `GLib.set_prgname()` is kept too, as the
  X11/WM_CLASS-matching fallback for window managers that don't use the
  Wayland app-id path.

## Follow-up: icon redesign, and progress bar had no visible motion

Two more rounds of real-desktop feedback:

- **Icon**: the nested-"A" concept was right but typed `<text>` glyphs
  render however the target's font stack happens to resolve DejaVu Sans —
  not guaranteed to look the same on every install. Replaced with two
  hand-authored cubic-bezier strokes (`icon.svg`) forming the same normal-A/
  rotated-A hourglass shape, verified via `Rsvg`+`cairo` render at
  256/48/24px — same silhouette, zero font dependency.
- **Progress bar had no visible motion**: the old per-item handler only set
  `fraction` twice (start-of-slot, end-of-slot), so between those two
  `idle_add` calls — the entire duration of the actual `apt`/`snap` removal
  or file delete — the bar just sat still, which read as "stuck" again, the
  exact complaint that started this whole thread. Fixed with
  `_start_progress_slice(start, end)`: a `GLib.timeout_add(60, …)` ticks the
  fraction up toward 92% of the current item's slice while the worker thread
  blocks on the real call, then the completion callback snaps to the exact
  boundary and sets the green/red CSS class. Same helper now drives leftover
  deletion too — `_run_leftover_cleanup_async` calls `clean_leftovers` one
  path at a time in the worker thread (instead of one blocking call for the
  whole list on the main thread after "Delete Selected") so that phase gets
  the same live green/red bar instead of a silent freeze.

## Displayed app name is "The Uninstaller"; project/repo name stays "Linux the Uninstaller"

User asked to shorten what actually shows in the window title bar, dock,
app grid, and alt-tab — those all come from one place each: the GTK window
`title`, `GLib.set_application_name`, and the `.desktop` file's `Name=`
(`gui.py`, `install.sh`). All three are now `"The Uninstaller"`. The
project/repo/README title is left as "Linux the Uninstaller" — that wasn't
part of the request and is the product's full name for docs/branding
purposes; only the live UI-facing strings changed.

## Leftover cleanup shows bytes freed

`delete_paths`/`clean_leftovers` now return `(bytes_freed, errors)` instead of
just `errors`. Size has to be measured with `leftovers.path_size()` *before*
`shutil.rmtree`/`unlink` runs — a deleted tree reports 0 bytes, so there's no
way to recover the number afterward. Only successfully-deleted paths count
toward the total (a failed delete didn't free anything). `format_size` moved
out of `App.size_human` into a module-level function in `models.py` so both
the app list's Size column and this new freed-space total share one
formatter instead of duplicating the KB/MB/GB rounding. Shown once via
`_info_dialog` when `_on_leftover_cleanup_done` fires, folded into the same
dialog as any delete errors rather than adding a second popup.

## apt uninstall: a nonzero exit doesn't mean the files are still there

Found on a real machine: a package (`trae`, a third-party `.deb`) whose
`postrm` script calls `db_purge` without sourcing
`/usr/share/debconf/confmodule` first — the function doesn't exist, the
script exits 127, and `apt-get purge` reports failure every single time,
forever, even though dpkg already deleted the package's actual files before
running that script (`dpkg -s` shows `install ok config-files`, not
`installed`). `uninstaller.py`'s `uninstall()` only calls `find_leftovers`
`if ok`, so this backend previously reported `ok=False` for a package that
was, for every practical purpose, already gone — which meant the leftover
dialog (and the new freed-space total) never appeared, silently, with no
error the user could act on beyond apt's raw stderr.

Fix: `AptBackend.uninstall` now falls back to reading dpkg's own status
field when the exit code is nonzero — `config-files` or `not-installed`
means the package's files are actually gone regardless of what the
maintainer script did, so it returns `ok=True` (unblocking the leftover
scan) with a message describing the cleanup error, which the GUI now shows
in its own "Removed, with a warning" dialog instead of dropping it (it used
to only ever surface `message` for the `ok=False` branch). A genuinely
broken purge (package still fully `installed`) still reports failure as
before.

## Freed-space total includes the app itself, not just leftovers

Tested on two real apps (`kiro`, `antigravity`, both Electron-style .debs)
that `apt purge` removed completely and cleanly — `find_leftovers` correctly
found nothing under `~/.config`/`~/.cache`/`~/.local/share`/`~/.var/app` for
either, verified against `find ~ -iname` directly. So the leftover dialog
never appeared, and the freed-space message added earlier (which only fired
from *that* dialog) never showed either — technically correct, but useless:
the actual freed space (the app's own hundreds of MB, already known from the
scan's `size_bytes`) was being thrown away.

Fixed by summing `app.size_bytes` over every successfully-uninstalled app in
`_on_uninstall_done` and carrying that total (`app_freed`) through the rest
of the flow — shown immediately if there are no leftovers to ask about, or
carried into `_offer_leftover_cleanup`/`_run_leftover_cleanup_async` and
added to whatever leftover bytes get deleted, so the one final dialog always
reflects the whole uninstall's freed space, not just the leftover remainder.

## SRS is Markdown, not a binary PDF, in version control

A PDF can't be diffed or reviewed in a PR. [SRS.md](SRS.md) is the source of
truth; export a PDF on demand with `pandoc` (one command, see README) rather
than adding a PDF-generation library as a project dependency for a document
that's read far more often than it's printed.

## Release artifact is a `git archive` tarball, not a built package

v0.1.0 ships as `linux-the-uninstaller-<version>.tar.gz`, produced by
`git archive` from the signed-off tag. The app is pure Python with no
compile step and no pip dependencies, so the "build" is just a snapshot of
the tree that `install.sh` already knows how to install from — `git archive`
does that in one command, honours `.gitignore` automatically (no
`__pycache__` or `dist/` leaking into the tarball), and needs no packaging
toolchain (`setuptools`/`build`/`dpkg-deb`) on the release machine.

Since the Linux build moved into `linux/`, the tarball is the `HEAD:linux`
tree plus the root `LICENSE` and `README.md` (`--add-file`). That keeps
`install.sh` at the tarball's top, where `selfupdate.install` looks for
`*/install.sh`. `git archive` has to run from the repo root (`git -C ..`):
run inside `linux/`, it keeps only paths under the current folder, which in
the `linux` tree means `linux/linux/`, and the tarball comes out empty.

A wheel/sdist via `python3 -m build` was rejected: `pip install` is not the
documented install path (the app deliberately uses system PyGObject rather
than a venv, see [Stack choice](#stack-choice)), so shipping a wheel would
advertise an install route that can't reach GTK. A `.deb` remains the right
long-term answer and stays in [features.md](features.md) as Planned — it's a
packaging feature with its own maintainer scripts and dependency
declarations, not something to improvise during a release.

## License: MIT

Chosen for a small desktop utility meant to be copied, forked and packaged
by distro maintainers without friction. GPL-3.0 was the plausible
alternative (Linux desktop norm) but its copyleft obligation buys nothing
here — there's no competitive moat to defend in a package-manager wrapper,
and permissive terms make it easier for someone to fold this into an
existing app store or distro package.

## Packaging: a staged tree and dpkg-deb

`build-deb.sh` stages `usr/` under `dist/deb/` and calls `dpkg-deb --build`.
No debhelper, no `dh_make`, no `debian/rules` — `dpkg-deb` is already on
every machine that can install the result, so the package has no build
dependency beyond dpkg itself. The full `debian/` apparatus pays for itself
when a package is multi-binary, patches upstream source, or goes into the
Debian archive; this is one arch-independent Python package with four
install locations.

Specific choices worth not re-litigating:

- **No `postinst`/`postrm`.** `desktop-file-utils` and `hicolor-icon-theme`
  ship dpkg *triggers* watching `/usr/share/applications` and
  `/usr/share/icons/hicolor`, so dropping files there refreshes both caches
  automatically. Maintainer scripts calling `update-desktop-database` by
  hand would duplicate a trigger that already fires, and a buggy one is the
  classic way to make a package unremovable.
- **`Depends: ... pkexec | policykit-1`.** `pkexec` moved out of
  `policykit-1` into its own binary package in newer Debian/Ubuntu; the
  alternation satisfies both, and declaring it at all is what keeps the
  privilege-escalation path (a non-negotiable, see CLAUDE.md) from silently
  being absent on a minimal install.
- **`.pyc` files are shipped**, built by `compileall` at package time.
  `/usr/lib` isn't writable by the user running the app, so Python would
  otherwise recompile every module on every launch and cache nothing.
  Because dpkg restores the `.py` mtimes the `.pyc` headers were stamped
  against, the shipped bytecode validates instead of being ignored.
- **`--root-owner-group`** instead of running the build under `fakeroot`:
  same root:root ownership in the archive, one flag, no wrapper process.
- **Version comes from `pyproject.toml`**, parsed by the build script, so a
  release bumps one number in one file.

---

# Stitches (Linux 0.2)

The Linux build grew from one uninstall list into seven tools and was renamed
twice: The Uninstaller → SoftHUB → **Stitches**. Everything above still holds
for the Uninstall page; this section covers what's new.

## The rename: what moved and what didn't

`src/uninstaller` → `src/stitches`, command `stitches`, GTK application id
`io.github.stitches` (the `.desktop` file and icon are named after it, same
Wayland rule as before), window/app/menu name "Stitches". This supersedes
"Displayed app name is 'The Uninstaller'" above. The `.deb` package is now
`stitches` with `Conflicts:`/`Replaces: softhub, linux-the-uninstaller`, so
installing it removes either older package instead of leaving two menu
entries; `install.sh` does the same for per-user copies under either earlier
name. The module `uninstaller.py` keeps its name: it still orchestrates one
uninstall.

**A rename unpins the app.** GNOME stores taskbar/dock pins
(`org.gnome.shell favorite-apps`) as `.desktop` file names, so deleting
`io.github.linux-the-uninstaller.desktop` made the pinned icon vanish; that
is what actually happened on the development machine after the first
reinstall. `install.sh` now rewrites that list after writing the new entry:
an old name becomes the new one in the same position, and a duplicate is
dropped. It uses python3 (already required) and does nothing where
`gsettings` or that key doesn't exist.

Windows and Android show "Stitches" wherever a person sees the name: window
title, `Stitches.exe`, `Stitches-<v>-x64.msi`, the Start menu and Apps &
Features entry, the Android app label and `Stitches-<v>.apk`. Their
identities stay: the MSI's `UpgradeCode` (so it upgrades an installed The
Uninstaller in place — the component got a new GUID, because its file and
folder names changed and a component keeps one key path for life), the
Windows AppUserModelID and `uninstaller` package, and Android's
`applicationId` and Kotlin package. Changing the applicationId would make
Android treat it as a different app, so installed copies could never update.

Deliberately not renamed: the repository and folder (the user will do that),
and `SRS.md`, which still describes 0.1.

## Window: a sidebar and a stack, one module per page

`gui.py` is now only the window: a dark sidebar (`Gtk.ListBox`) switching a
`Gtk.Stack`. `Gtk.StackSidebar` was the native option, but it can't carry an
icon or a count badge per row, and the approved design has both; a ListBox
row with an icon, a label and a badge is about fifteen lines. Each tool is
its own module under `pages/`, and what they share lives in `widgets.py`:
the `Page` scaffold (title, subtitle, action bar), the checkbox table, the
tag markup and the confirm/info dialogs. The 0.1 note that one window stays
one module was right for one screen; five screens of ~150–250 lines each
are five responsibilities. (The sidebar was later replaced by a dock — see
*Third round* below; the stack and the page modules didn't change.)

Styling is one CSS block in `widgets.py`, and it only colours what the
design fixes regardless of theme: the sidebar and the action bar (always
dark), and the accent. Page backgrounds and cards use `@theme_bg_color` /
`@theme_base_color`, so the existing light/dark switch (moved into the
sidebar) keeps working with every theme exactly as before. The design's
Geist font isn't bundled; the system font is used.

Tags (source, risk) are Pango `background` spans inside `TreeView` cells.
Rounded pill corners would need a custom cell renderer or a `ListBox` of
widgets per row; the TreeView was kept because Uninstall lists 300+ rows
with filtering, and square-cornered tags were the cheap trade.

A page locks only itself while it works (`Page.set_busy`), not the whole
window, so an update can run while you look at another tool. The cost: two
pages can start apt at once, and the second fails with apt's own "Could not
get lock" message — honest, and rare enough not to warrant a global lock.

## The line loader

The requested "straight line loading" is a `Gtk.ProgressBar` restyled to a
3px glowing line along the top edge of each page's action bar. It pulses
(`pulse()`) while scanning, and while work runs it reuses 0.1's crawl-toward-
92%-then-snap approach (`ActionBar.slice/settle`), because apt, snap,
fwupd and e4defrag report no progress we can read. It's accent-blue while
working and red once anything fails; the 0.1 green-on-success colour was
dropped for the design's accent.

## `shell.py`: C locale, nothing on stdin

Every new module reads other programs through `shell.output()`, which runs
them with `LC_ALL=C` and stdin at `/dev/null`. The C locale is not
hypothetical: the development machine runs a Bengali locale, and apt,
flatpak and snap translate the very strings the parsers match
(`[upgradable from: …]`, `Nothing unused to uninstall`). The empty stdin
means no tool can ever sit waiting for an answer nobody can see.
`shell.run()` is for commands that change something: it returns stdout and
stderr together, stderr last, so a failure's reason is at the tail the GUI
shows.

## Updates

| Source | Found with | Updated with |
|---|---|---|
| APT | `apt list --upgradable` + one `apt-cache policy` for the repo host | `pkexec apt-get install --only-upgrade -y …` |
| Snap | `snap refresh --list` + `snap list` for the installed version | `pkexec snap refresh …` |
| Flatpak | `flatpak remote-ls --updates` + `flatpak list` | `flatpak update -y --noninteractive <ref>` |
| GitHub | an AppImage's embedded update info + the GitHub releases API | download, verify, swap in place |

- **"From a website" means a vendor repo.** A `.deb` downloaded from a
  website has no update feed, so nothing can check it (features.md, out of
  scope). A vendor that ships an apt repo does, and `apt-cache policy`
  names the host, so VS Code shows `packages.microsoft.com` rather than
  looking like a distro package.
- **APT and Snap update as one batch each.** `pkexec` asks for a password
  every time; one per package would make bulk update unusable. The cost is
  that per-package progress inside a batch isn't visible, so the whole
  batch shares one status. Flatpak and AppImages need no password and go
  one at a time.
- **No `apt update` first.** It needs root, so every "Check again" would
  cost a password. The list is as fresh as the system's own daily refresh.
- **`--force-confdef --force-confold`.** There's no terminal to answer
  dpkg's "keep your changed config file?" question, and an unanswered
  prompt fails the whole run. Keeping the user's file is also apt's own
  default.
- **GitHub AppImages.** Every AppImage carries an ELF section `.upd_info`;
  the common form is `gh-releases-zsync|owner|repo|tag|glob.zsync`.
  `read_update_info` reads it with `struct`, no extraction and no running
  the binary. The newest matching release asset is compared **by size** to
  the local file (`ponytail:` in the code) — sizes of compressed images
  essentially never repeat across builds, while hashing would read every
  AppImage on each check. The download goes to `<file>.part`, must match
  the asset's size and, when GitHub publishes one, its sha256 `digest`, and
  only then replaces the file under the same name, so launchers that point
  at the path keep working. A cut-off download never replaces a working
  app.
- The four sources are checked in parallel (`ThreadPoolExecutor`): three
  of them wait on the network.

## Cleanup

Each `Location` carries either paths to delete as the user, or a command
to run, plus the `(what, bytes)` lines the removal log shows:

| Location | How | Risk |
|---|---|---|
| APT package cache | `pkexec apt-get clean` | Safe |
| Old Snap revisions | `pkexec sh -c 'snap remove X --revision=N && …'` | Safe |
| App caches (`~/.cache/*` except thumbnails) | delete per child | Safe |
| Thumbnails | delete per child | Safe |
| Logs older than 7 days | `pkexec journalctl --vacuum-time=7d` | Safe |
| Unused Flatpak runtimes | `flatpak uninstall --unused -y` | Caution |
| Temp files older than a day | delete per entry | Caution |
| Trash | `gio trash --empty` | Caution |

- Nothing is pre-selected (Safe ones were, until the fourth round); removal
  always goes through the confirmation dialog (CLAUDE.md).
- **Unused Flatpak runtimes are listed by asking flatpak.** Working out
  "unused" ourselves means reimplementing flatpak's knowledge of
  extensions, SDKs and GL drivers — wrong answers delete things apps need.
  `flatpak uninstall --unused` prints its list and then asks to proceed;
  with no terminal it answers no by itself (why CI scripts need `-y`), and
  "n" is piped to stdin as well.
- **Temp files: only the user's own, untouched for a day, and holding no
  socket anywhere inside.** A running ssh-agent or tmux keeps its socket
  in a `/tmp` directory for its whole life, often longer than a day;
  deleting it breaks the session. `is_stale` walks the entry once for
  both the socket check and the newest mtime.
- For command locations the log shows the sizes measured at scan time,
  since `apt-get clean` and friends don't report per-item sizes.
- One password prompt per admin location (up to three); see features.md.

## Drivers

On Linux most drivers are part of the kernel and update with it; what
updates separately comes from three places, and the page says so rather
than pretending to a Windows-style driver catalogue:

- **`ubuntu-drivers devices`**: devices with a proprietary driver (mostly
  NVIDIA). An update means the recommended package isn't the installed one;
  it's installed with `apt-get install`, like `ubuntu-drivers install`
  does.
- **fwupd/LVFS**: devices come from `fwupdmgr get-devices --json` (only
  those flagged `updatable`), updates from `get-updates --json`.
  `get-devices` embeds `Releases` too, but those include releases that
  aren't upgrades (seen on this machine: a KEK certificate offering its
  own current version), so only `get-updates` decides. Flashing runs as
  `pkexec fwupdmgr update <id> --assume-yes --no-reboot-check`; UEFI
  firmware lands on the next reboot, and the page says so.
- **`linux-firmware*`** from `apt list --upgradable`. It also appears on
  Updates; that's deliberate, since it's where people look for it.

The device list is PCI devices in the classes someone would recognise
(display, network, audio, storage, wireless) from `lspci -vmmnnkD`, shown
with the kernel driver in use. Names keep a GPU's bracketed marketing name
("Radeon R7 240") but not other brackets, which say things like
"[AHCI Mode]".

The system spec (on Home since the second round) reads `/etc/os-release`,
`/proc/cpuinfo`, `/proc/meminfo` and `/sys/class/dmi/id` directly. Two details: self-built desktops report
"System manufacturer / System Product Name" in DMI, so those placeholders
fall back to the board's vendor and name; and disk models come from
`lsblk`, because `/sys/block/*/device/model` cuts ATA models at 16
characters.

## Defrag

ext4 (`e4defrag`), btrfs (`btrfs filesystem defragment -r`) and XFS
(`xfs_fsr`) are the filesystems Linux can defragment online, all run as
root on the mountpoint. Every drive with a filesystem is listed, and the
ones that won't be touched say why: an SSD (no benefit, and wear), not
mounted, a filesystem with no Linux defragmenter (NTFS, FAT, exFAT), or a
missing tool package. btrfs is marked "unshares snapshots": defragmenting
copies extents that snapshots share, which can use more space.

There's no "Analyze" step, although the design had one: `e4defrag -c` run
unprivileged prints nothing, so a fragmentation score would cost a
password prompt just to look. `e4defrag` itself skips files that aren't
fragmented, so running it is its own analysis.

## Second round: Home, Diagnose, themes, self-update

### Home: numbers with a verdict

The spec moved off Drivers to Home, and the request was "not just numbers":
every reading carries Good / Warning / Critical, and every BIOS setting a
sentence saying what it does. `sysinfo.describe_firmware` is pure over a
facts dict, so the wording is tested; the facts come from files any user can
read — `/sys/class/dmi/id` (BIOS vendor, version, date), `/sys/firmware/efi`
(UEFI or legacy), the `SecureBoot-8be4…` efivar (last byte is the value),
`/sys/class/tpm`, and the `vmx`/`svm` CPU flag plus `/dev/kvm`. A BIOS can't
be read "settings-wise" beyond that without root and vendor tools, so those
five are the settings shown.

Temperatures come from hwmon (`/sys/class/hwmon/*/temp*_input`) and use the
chip's own `max`/`crit` when it reports them — coretemp says 80°/100° — with
Critical starting 5° short of the chip's critical point, and 75°/90° when a
chip reports nothing. A CPU with many cores collapses to its package reading
plus "hottest of N more". Drive temperatures come from SMART via UDisks2.
Fans are `fan*_input`; many desktop boards expose none until their sensor-chip
driver (`nct6775`, `it87`) is loaded, and Home says exactly that instead of
showing an empty card. Live values refresh every 5 seconds, only while Home is
on screen.

Partition usage is one `lsblk -o …,FSUSED,FSSIZE` call rather than statvfs
per mount, because lsblk also lists the partitions that aren't mounted (their
usage is unknown until they are, and the page says so).

### UDisks2 through `busctl --json`, not Gio

SMART health comes from UDisks2 — the same source GNOME Disks uses, readable
without root, nothing to install. It's fetched with
`busctl --system --json=short call … GetManagedObjects` and parsed as JSON,
rather than through `gi.repository.Gio`, so `vitals.py` and `diagnose.py`
import nothing from GObject and their tests run on a CI runner without
PyGObject. ATA drives report `SmartFailing`, bad sectors and failing
attributes; NVMe reports a `SmartCriticalWarning` list; temperatures are in
kelvin. A drive with no SMART data (USB sticks, some adapters) is "Info", not
a failure.

### Diagnose: the Windows tools, mapped

| Check | Stands in for | How | Fix |
|---|---|---|---|
| System files | `sfc /scannow` | `dpkg --verify` as the user | `apt-get install --reinstall` the owning packages |
| Package database | `DISM /CheckHealth` | `dpkg --audit`, `apt-get check -o Debug::NoLocking=1` | `dpkg --configure -a && apt-get -f install` |
| Disk health | CrystalDiskInfo | UDisks2 SMART | — |
| File systems | `chkdsk` | `/sys/fs/ext4/*/errors_count` | `tune2fs -E force_fsck`, then restart |
| Memory, quick | Memory Diagnostic | pattern test in-process | — |
| Memory, full | Memory Diagnostic (restart) | memtest86+ via `grub-reboot` | restart |
| Free space, Services, Errors since startup | Storage Sense, services.msc, Event Viewer | lsblk, `systemctl --failed`, `journalctl -b -p err -o json` | restart failed services |

Decisions worth keeping:

- **Every check reads without a password.** `dpkg --verify` works as the user
  (about 70–80 s on a desktop install; files only root can read report "?" and
  are counted as "can only be checked with admin rights", not as damage).
  Config files are skipped, since they're meant to be edited, and so are
  diversion targets: Zorin diverts `/etc/gtk-3.0/settings.ini` and
  `dpkg --verify` reports the moved original "missing", which was the one
  false positive on the development machine. `apt-get check` needs the dpkg
  lock unless told `Debug::NoLocking=1`; it only reads, so that's safe.
- **Diagnose doesn't scan on its own.** Every other page scans when the window
  opens; this one reads every installed file, so it waits for **Scan**.
- **The quick memory test is honest about its reach.** It writes five
  patterns over up to 1 GiB (a quarter of what's free) and compares them in
  1 MiB slices; a `bytearray` slice comparison is a memcmp, while comparing
  `memoryview` slices goes byte by byte and took 17 s instead of 3. It can
  only test memory the kernel hands it, and the result says so.
- **Restart fixes set the next boot only, and ask twice.** The full memory test
  uses `grub-reboot memtest86+` (the menu entry's id, so it doesn't depend on
  the translated title). `grub-reboot` works regardless of `GRUB_DEFAULT`,
  because `00_header` always honours `next_entry` and clears it after one use.
  With Secure Boot on, unsigned memtest86+ may be refused by the firmware, and
  the caution says that before anything is set. A file-system check at restart
  uses `tune2fs -E force_fsck`, e2fsprogs' own "check at next mount" flag, which
  systemd-fsck acts on at boot. Both fixes explain what will happen, and then
  a second dialog asks before actually restarting.

### Drivers say what each thing is

The question was "is this even for Linux?" — fair, since "KEK CA" and
"linux-firmware-amd-graphics" explain nothing. Each row now carries a
`purpose` in its own **What it is** column: fwupd items are mapped by plugin
(`uefi_capsule` is the motherboard's BIOS, other `uefi_*` are Secure Boot key
lists, `ata`/`nvme` is the drive's own firmware…) and all say they apply to
every OS, because they run inside the hardware. `linux-firmware*` says which
chips it's for and that it's Linux only; kernel drivers say they update with
the kernel. The source moved under the version to keep the table inside a
1180 px window.

### Stitches lists itself

A per-user install from `install.sh` lives in `~/.local`, which no package
manager knows about, so the one app Stitches couldn't list was itself. That was
the exact situation on the development machine (an old 0.1 install). A
fifth backend, `local_backend.py`, recognises this app's own install layout
(under its current name and both earlier ones) and removes exactly what
`install.sh` places.
It deliberately doesn't try to find other script-installed apps: there's no
common layout to recognise, and guessing what to delete is the wrong kind of
guess. If it's the running copy it's rated Caution. `backends/base.py` is
left untouched (its docstring still says four) because it's kept
byte-identical with the Windows copy.

### Themes

Light and Dark are still the system theme's own variants. AMOLED and Glass
are extra CSS loaded one priority step above the base CSS, both on the dark
variant for its text colours. Glass is translucency, not blur: GTK3 can't
blur what's behind a window. The window asks for an RGBA visual whenever the
screen is composited; opaque themes simply paint over it. Theme choice is
stored in `~/.config/stitches/settings.json`; the 0.1 note about deferring
persistence until someone asks is answered.

Buttons that only repeat an action's name (refresh; select all/none/safe until the
fourth round replaced them with a header checkbox) are icon-only
with the name on hover. Buttons that carry a count or change the system
(Update selected · 14, Remove selected · 9.5 GB) keep their words.

### Update all (removed in the fifth round)

Updates and Drivers each got **Update all**: every pending item, no ticking.
It went through the same batching as Update selected, so APT and Snap still
asked for the password once each. The fifth round removed it: the
select-all circle does the same in two clicks, and two buttons that both
update read as a choice that isn't one.

### Self-update from GitHub releases

`selfupdate.py` asks `api.github.com/…/releases/latest` once at start-up on a
thread; offline or rate-limited just means no notice, never an error. A newer
tag shows a toast that dismisses itself after 4 seconds (10 before the fourth
round), and marks the
dock's update button. Installing picks the asset matching how this copy
got here, decided from its own path: `/usr/…` is a `.deb` install, so it
downloads `stitches_*_all.deb` and runs `pkexec apt-get install` on it;
`~/.local/lib/…` is `install.sh`'s, so it downloads `stitches-*.tar.gz`,
extracts it (with the `data` filter where Python has it) and runs its
`install.sh`; a git checkout is told to `git pull`. Downloads go through the
same `updates.download()` as AppImages: size and GitHub's sha256 digest must
match before anything is installed. Restart is `os.execv` of the same
interpreter, which keeps the launcher's `PYTHONPATH`.

`REPO` still names `Redwan-Shawkat/The-Uninstaller`. GitHub redirects the API
after a rename, so it keeps working, but update it when the repo is renamed.

### Releasing is pushing a tag

Every release needs the `.deb` and the tarball for the self-updater to work,
so `linux-build.yml` builds both on a `v*` tag instead of relying on someone
uploading them. The three workflows run in parallel. Previously each ran
`gh release upload`, which fails if no release exists, and each uploaded
`SHA256SUMS.txt` with `--clobber`, so the last one overwrote the other two.
Now each first tries `gh release create` (the first to finish wins, the
others' "already exists" is ignored) and uploads its own
`SHA256SUMS-<platform>.txt`.

## Real screenshots without the screenshot portal

The Screenshots note in the README says GNOME's screenshot APIs refused a
non-interactive caller. `Gtk.Widget.draw()` onto a cairo image surface
renders the real, running window, from inside the process, on Wayland too,
with no portal involved. That is how the 0.2 pages were checked visually
during development. The window does open on the desktop while this runs:
a click on it changes the page (or the theme) between two captures, and a
hidden window (on Wayland) stops being laid out, so a capture can come back
stale. Check which dock icon is lit in the image before trusting it.

## Third round: a dock, a sewn logo, a compact Home

### A dock instead of a sidebar

The tools moved from a left sidebar to one row of icons centred under the
page, like a desktop dock (the request: "no sidebar… a dock at center").
The buttons are one `Gtk.RadioButton` group with `draw_indicator=False`,
which GTK renders as plain buttons with `:checked` on the open tool — the
radio group is what keeps exactly one lit, so there's no selection code.
Each icon sits in a `Gtk.Overlay` with 4 px of margin, so the count badge
lands in the corner instead of on the icon. Names and counts are the
tooltip. The dock is packed under the stack, not overlaid on it: overlaid,
it would cover every page's action bar. The collapse button and its
`collapsed` setting went with the sidebar; an old settings file that still
has the key is simply ignored. The dock stayed dark in the Light theme, like
the action bar above it, until the fourth round gave it its own theme.

### The sewn logo

Asked for "the same logo, but like catch stitches". Kept: the tile, the
colours and the A-over-V curves. Added: `stroke-dasharray` on both curves,
so they read as thread between needle holes, and a dashed rounded rect
inside the tile edge, the running stitch of a sewn-on patch. Tried and
dropped: straight lines with overshooting tips (a literal catch-stitch
diagram) and over/under gaps at the crossings. At 30 px both read as a
broken "AV", not as stitching. Windows (`tools/make_icon.py`) and Android
(a vector drawable, which has no dash support) still draw the plain curves.

### Compact Home

Everything on one screen at the default 1180×760 window. Home is three
equal columns (This PC + Memory, BIOS/UEFI, Temperatures & fans) above a
full-width storage strip. The last card in each column stretched, so the
columns ended level; the fourth round undid that (cards only as tall as
their content). A `compact` CSS class sets 12 px labels and 11 px notes
on Home only; other pages keep their size. Fans became a line inside the
temperatures card, because on most desktops without the sensor driver the
Fans card held one sentence. Unmounted partitions are one line ("sda2 ntfs
200 GB · …") instead of a row each. The page still sits in a
`ScrolledWindow`, so a smaller window scrolls instead of clipping. Page
titles went from 26 to 22 px on every page, with tighter header margins,
to make room for the dock.

## Fourth round: groups, mixed themes, and saying more per page

### The icon that didn't show, and the logo that didn't look sewn

**Missing icon.** The pin and the `.desktop` file were right, and
`Gtk.IconTheme` found the SVG, yet GNOME Shell showed a generic icon. GTK
(and St, the Shell's copy of `GtkIconTheme`) only rescans an icon theme when
the mtime of the theme's *top* folder (`~/.local/share/icons/hicolor`)
changes. The icon goes into `scalable/apps`, which only changes that
subfolder's mtime. `gtk-update-icon-cache` would have touched the top
folder, but it refuses to run on a user folder with no `index.theme`, and
`|| true` hid that. A Shell started before the icon was installed therefore
never saw it. `install.sh` and `uninstall.sh` now `touch` the top folder.
This is the old RPM-scriptlet idiom, and the reason for it.

**Not stitched.** The dashed curves used round caps as wide as the gaps (7
units each), and each cap reaches half its width past the dash end. So the
caps met and closed every gap: at dock size (30 px) the thread was a solid
line. Now:
- the thread has square caps, 9 on and 6 off, with the width down to 6;
- each curve is 129 units long, so that pattern puts a stitch on both tips
  and on the apex (tested at 24, 30, 48, 64 and 128 px);
- a faint 2-unit seam line runs underneath, so the A/V shape still reads
  where the gaps fall;
- the border stitch is lighter (`#6b7280`) and thicker, so it survives 30 px.

### Dock groups and mixed themes

The dock is now `Icon | Home | Diagnose, Cleanup | Updates, Uninstall |
Drivers, Defrag | theme, update` (the fifth round made the logo the Home
button). The window holds `self.groups`, a list of
page lists, and `self.pages` is that flattened. The dock puts a separator
before each group, and the radio group still runs across all of them.

The window and the dock each take one of the four themes, so any mix works
("dark, only nav white", "light with a black or glass dock"). `DOCK_CSS`
(Light, AMOLED, Glass; Dark is the base `CSS`) is concatenated onto
`THEME_CSS` and loaded into the same provider. `THEME_CSS` no longer styles
`.dock`, so the two choices can't fight. The popover shows two radio columns,
Window and Dock. `_apply_theme(theme=None, dock=None)` writes both settings
*before* moving any radio, because moving one calls straight back into it.
A settings file from before the split has no `dock` key; it then follows
the old behaviour (AMOLED and Glass styled the dock, other themes kept it
dark), so nobody's dock changes on upgrade.

### Home: cards only as tall as what they hold (no cards since the fifth round)

The last card in each column no longer stretches, and the columns are
`valign=START`, so leftover height sits below the cards, not inside them.
The gaps are 8 px. Fixing that turned up a GTK3 trap: a container works out
its size-request mode (height-for-width or constant) the first time it's
measured, and never again. Home's grids are empty until the readings arrive.
So they, and every box above them, settled on constant-size, and sized each
wrapping label as if squeezed to one word per line (This PC asked for 368 px
to show 208). Each grid now starts with a wrapping "Reading…" note. That
fixes the mode, and it's a useful placeholder anyway. The same applies to
any container filled later with wrapping labels: give it one from the start.

### Diagnose shows its output as it happens

An output panel (dark, monospace, next to the checks; titled Terminal
since the fifth round) shows each check's
name, every command it runs (`$ …`, in the accent colour), what that command
prints, and the verdict coloured by status. A fix's own output streams there
too, so a reinstall of packages is watched line by line.

- **`shell`.** `output()` and `run()` take `on_line`: `Popen`, read `stdout`
  line by line, and hand each line over as it arrives.
  - `output()` keeps `stderr` out: its callers parse `stdout`, and a stray
    warning line would read as a failed unit.
  - `run()` merges `stderr` in, since for a fix the user wants all of it, in
    order.
- **The checks.** Each one takes `log`, and `run_check(check, log)` frames it
  with the name and the result.
  - JSON output (`journalctl -o json`) is logged as its command only: it's
    no use to read.
  - Checks that go through `vitals` (UDisks2, `lsblk`) log a line saying
    what they read, since nothing there prints.
- **The page.** `log` comes from the worker thread, so `_log` passes each
  line on through `GLib.idle_add`.

### One select-all circle, and nothing ticked at first

The select-all/none icon buttons in the action bars are gone (and so is
Cleanup's "select safe only"). The ticks' column header holds a checkbox
instead:
- `make_table(..., on_toggle_all=)` sets it as the column's header widget;
- the column is clickable, because the header button takes the click, not
  the checkbox inside it;
- `make_table` returns it as a third value;
- `show_select_all()` keeps it ticked, unticked or dashed as rows change;
- CSS rounds it to match the round row ticks this theme draws.

What "all" means is per page:
- **Updates and Uninstall:** only the rows the search and source filter
  leave on screen. Changing the filter re-syncs the header.
- **Uninstall:** also skips Critical rows. They stay one at a time, as
  "Select all non-critical" did.
- **Drivers and Defrag:** skips rows with nothing to do.

No page pre-selects anything any more. That includes Updates, which ticked
everything, and Cleanup, which ticked Safe.

### Cleanup says what it touches

Cleanup now says what it removes in two places:
- **A card above the removal log** (the fifth round cut it to one line
  in the action bar). Only rebuildable or re-downloadable things go. Your files, settings and passwords stay. Every installed app
  stays installed. The Trash is the one exception.
- **The reason, in its own column** (with the risk tag at its end since
  the fifth round). It was only a tooltip before. Each
  reason was reworded to say whether software or personal data is involved,
  e.g. Snap: "every app stays installed, at the version you use"; Trash:
  "this is your own data".

### Drivers: when it was released, and a source icon

A Released column shows when the maker released the version on offer: the
new one if there's an update, else the installed one.

| Row | Date comes from |
|---|---|
| APT packages (`ubuntu-drivers`, `linux-firmware`) | The first sign-off line of the changelog: `/usr/share/doc/<pkg>/changelog.Debian.gz` for the installed version, `timeout 10 apt-get changelog <pkg>` for a waiting update (1–2 s each; the one on disk is the old version's). |
| Kernel drivers | The same, for `linux-image-$(uname -r)`. `uname -v` isn't used: the kernel truncates it to 64 characters, cutting off the year. |
| fwupd | The LVFS release's `Created` for that version. For the BIOS itself (`uefi_capsule`), the board's `/sys/class/dmi/id/bios_date` when LVFS has nothing. Anything else with no release published shows "—". |

The source moved out of the Driver column into an icon column: computer
(kernel), download (ubuntu-drivers), cloud (LVFS), package (linux-firmware).
A click opens a popover naming the source and what it is. The click is
found with `get_path_at_pos` on `button-release-event`, and the popover
points at `get_cell_area`, converted from bin-window to widget coordinates.
Screenshots from `Gtk.Widget.draw()` draw every popover at the window's
top-left, the stock theme menu included. That's the capture, not the
placement.

### Defrag: tiles, grouped by OS

Partitions are grouped Linux, Windows, macOS, Boot and Other, by `os_of()`:
the GPT partition type lsblk reports (`PARTTYPENAME`: "Microsoft basic
data", "Windows recovery environment", "EFI System", "Linux filesystem"),
else the filesystem.
- **Tiles.** Each group is a `Gtk.FlowBox` of tiles, side by side, 2–4 per
  line (each tile a card of its own until the fifth round). A tile has a drive icon (HDD, SSD, USB), a name (mount point, else
  the partition label, else "Not mounted"), the device, filesystem, size and
  kind, and the status.
- **Ticking.** Only Ready drives get a checkbox. A group with any Ready drive
  gets one in its heading that ticks them all. Keeping the heading in step
  calls `set_active()`, which fires `toggled`, so the sync runs inside
  `handler_block`.

### The update notice: 4 seconds, and a line that runs down

`_TOAST_SECONDS` went from 10 to 4. A timed toast now runs
`ActionBar.countdown()`: the bar's line starts full and shrinks to nothing,
timed against `GLib.get_monotonic_time()` so it doesn't drift, then the toast
hides. Busy toasts still sweep, and toasts with no timeout still stay up.
`settle()` now shows the line as well, so a failed self-update's red line
appears instead of settling on a hidden bar.

## Fifth round: fewer boxes, fewer buttons

### The logo is Home

The dock's logo was a picture next to a Home button. Now it *is* the Home
button: `HomePage` has no `icon`, and `_dock_button` gives an icon-less page
the logo at 26 px (the 18 px icons plus their 4 px margins), so every
button in the dock is the same size. The dock reads `Home (logo) |
Diagnose, Cleanup | Updates, Uninstall | Drivers, Defrag | theme, update`.

### Our own icons, and stand-ins

Uninstall's icon was a trash can, which says "delete a file". There's no
standard name for "uninstall an app": GNOME Software's `app-remove-symbolic`
is a trash can too. So `icons/stitches-uninstall-symbolic.svg` draws an app
grid with one tile taken out (a minus where it was). Drivers moved from the
firmware icon to `cpu-symbolic`, a chip. Diagnose went from a shield (which
says security) to `device-diagnostics-symbolic`, a screen with a magnifier,
the icon GNOME Settings uses for its own Diagnostics. Cleanup went from a
crossed circle (which says cancel) to `tool-brush-symbolic`, a brush.

`main()` adds `src/stitches/icons/` with `IconTheme.append_search_path()`.
GTK3 looks there *after* the icon theme and its parents, so it serves two
purposes:
- **Our own names** (`stitches-uninstall-symbolic`), found only there.
- **Stand-ins** for names only some themes have: `cpu`, `memory`,
  `sensors-temperature`, `device-diagnostics`, `tool-brush`. Zorin has them; Adwaita doesn't. A theme that has
  one still wins, so the icons match the desktop where they can.

Loose `-symbolic.svg` files in a search path are recoloured like themed
ones, so they follow the dock and theme colours. `build-deb.sh` and
`install.sh` copy the whole package folder, so `icons/` travels with it.

### Home: groups, not cards

The Home cards are gone. Each section is a group: a small accent-coloured
icon and its title over the grid (computer, firmware, thermometer, RAM,
drive). With no borders, the space between groups (18 px) is what sets
them apart. The GTK3 "Reading…" placeholder is still needed: it's about the
grid, not the card.

### Cleanup: one table, a filter, the risk inline

- **The explanation card is gone.** The action bar now reads "Removes only
  what gets rebuilt or downloaded again. Your files and installed apps stay;
  Trash is the one exception." Each row's own reason already says what that
  row means.
- **No Risk column.** The risk tag sits at the end of the reason, in the
  same wrapped cell, so a column isn't spent on one word.
- **A filter** in the header, like Updates and Uninstall: All locations,
  Safe, Caution, No password needed. `_FILTERS` maps each name to a test on
  the `Location`. The table shows a `TreeModelFilter`, so ticks convert the
  path to the store's, and the select-all circle covers only what the filter
  shows (the same `_shown()` pattern as Updates). A ticked row that gets
  filtered out stays ticked, and the confirm dialog still lists it.
- **The "Removed from" log moves under the table when the window is narrow.**
  The table sits in a sideways-scrolling card, so in a window narrower than
  table + log (about 940 px) the SIZE column scrolled out of sight and the
  "password" tags were cut to "…". The body box listens to `size-allocate`
  and switches to vertical once its width is below the tree's natural
  width + the log card's + 40 (borders, spacing, scrollbar). The switch goes
  through `idle_add`, because GTK can't take an orientation change in the
  middle of an allocation. The numbers come from the widgets, not a fixed
  breakpoint, so they stay right when a column changes.

### Drivers: no log, no Update all

The Update log card on the right was empty on every launch until something
was updated, and nothing kept it between runs. It's gone. Like Updates, a
driver update that fails now opens a dialog with the end of what it printed
(`tail(text, 4)` per job), and the action bar says how many went through.
The table gets the full width.

### Defrag: one card per group

Tiles lost their own cards. Each OS group is a single card, with its heading
and all its tiles side by side inside it, and wider column spacing (24 px)
so the tiles stay apart without borders.

---

# Windows port (`windows/`)

## A sibling tree, not one cross-platform package

`windows/` is a parallel copy of the project, not a `if sys.platform` layer
inside `linux/src/stitches`. The two builds share the *shape* — `models.py`,
`risk.py`, `leftovers.py`, `scanner.py`, `uninstaller.py` and a `backends/`
directory with one file per source — and share almost none of the *code*,
because every leaf is platform-specific: the backends shell out to different
tools, the GUI uses a different toolkit, escalation uses a different
mechanism. A merged tree would be four files of genuinely shared logic
(`format_size`, `App`, `path_size`, `delete_paths`) wrapped in platform
branches everywhere else, and every Windows change would risk the Linux
build. Two trees, one architecture: a reader who knows one knows the other.
The identical module names are the point.

The Linux build started at the repo root and was later moved into `linux/`,
so all three builds are sibling folders and the root holds only what they
share (README, LICENSE, `documents/`, CI). Its scripts resolve paths from
their own location, so the move changed no code, only documented commands.

Kept byte-identical on purpose so the correspondence stays obvious:
`uninstaller.py` and the `Backend` protocol in `backends/base.py`.

## GUI: tkinter, not GTK3

Same rung of the ladder as the Linux build, pointing the other way. There,
PyGObject/GTK3 is already installed on every Ubuntu desktop and adds zero
packages. On Windows nothing GTK is present and shipping it means
redistributing an MSYS2 runtime — several hundred megabytes attached to a
~10 MB app. tkinter is in the Python standard library on Windows, so it costs
nothing to import and nothing to freeze, and PyInstaller has understood it
for years.

What that costs, and what was done about it:

- **No filter model.** GTK's `Gtk.TreeModelFilter` does live filtering for
  free; a `ttk.Treeview` holds rows and nothing else. `_refresh_rows()` just
  refills it. Marked `ponytail:` — a few hundred rows refill instantly, and
  an incremental diff can replace it if a machine turns up where they don't.
- **No checkbox cell renderer.** The selection column holds `☑`/`☐` and a
  `<Button-1>` handler toggles it. The source of truth is `self.selected`, a
  set of indices, not the widget — so filtering can't silently drop a
  selection the way re-rendering a checkbox column would.
- **No tooltips.** The risk *reason* is the point of the risk column, so it
  got a ~20-line `_Tooltip` rather than being dropped.
- **No theming that respects colours.** ttk's native `vista` theme draws
  through the OS and ignores configured colours, including the progress
  bar's green/red. So `clam` backs *both* light and dark, with two palettes
  in `_PALETTES`. Slightly less native-looking than `vista`; in exchange the
  dark mode and the success/failure colours actually work, on every Windows
  version, with no theme-specific special-casing. The Linux build gets this
  free from the system theme — this is the one place the Windows UI is
  visibly its own thing.

Threading is the same design: work on a daemon thread, results marshalled
back with `self.after(0, …)` — tkinter's equivalent of `GLib.idle_add`, and
equally non-negotiable, since touching widgets off the main thread corrupts
Tk's interpreter state.

## GUI look: "Graphite & Signal"

The Windows window was redesigned from a mockup (dark graphite, one lime
accent, disk space as the headline) rather than aiming for a native Fluent
look, which `clam` can't reach anyway. What was decided, and why:

- **System fonts only.** The mockup used Bricolage Grotesque and IBM Plex;
  the app uses Segoe UI Variable (Windows 11) → Segoe UI, and Cascadia Mono →
  Consolas, picked by `_pick_family` from what's installed. Bundling font
  files would mean registering them per process (`AddFontResourceEx`) and
  shipping licences for a cosmetic gain — not worth it.
- **Dark is the default**, light is the toggle. Both palettes live in
  `_PALETTES`; source colours are keyed by `Source` in the same dicts.
- **The disk bar is the source filter** (the old combobox is gone). A
  `tk.Canvas` of rectangles sized by bytes per source. Only registry
  installs report a size today, so Store/Chocolatey/Scoop get a minimum
  clickable sliver, and the bar falls back to app counts when no source has
  a size at all. Canvases have no alpha, so an inactive segment is a colour
  blended toward the background (`_blend`).
- **Risk is a shape as well as a colour** (● safe, ▲ caution, ■ critical),
  so it doesn't depend on telling red from green. A Treeview can only colour
  whole rows, so the coloured shape is a 12px `PhotoImage` in the tree
  column (`_glyph_image`), redrawn per palette.
- **The selection is a "Removal tray"** — a Listbox beside the list with a
  running total of the space it frees. It mirrors `self.selected`; the
  source of truth is unchanged.
- **A click anywhere on a row toggles it; Shift+click adds a range.** The
  first cut toggled only from a `+`/`✓` column at the far right, which the
  default window clipped off-screen — nothing was selectable. Whole-row
  clicks can't clip. The range skips Critical rows, the same rule as
  Select All; hovering (the risk tooltip) still selects nothing.
- **The list is sorted biggest first** on every scan: the reason to open an
  uninstaller is usually disk space.
- **Leftovers start unticked** (they were pre-ticked). The dialog says
  "nothing goes unless you tick it", which is the opt-in the non-negotiables
  ask for; the Android build's planned list has the same concern.

## The four sources, and why `winget` isn't one of them

The Linux build's four sources are four separate places a program can hide.
Windows' are:

| Source | Read from | Why it's separate |
|---|---|---|
| Installer (MSI/EXE) | `…\CurrentVersion\Uninstall`, all three registry views | What Apps & Features shows. |
| Microsoft Store | `Get-AppxPackage` | MSIX packages register no Uninstall key at all. |
| Chocolatey | `$ChocolateyInstall\lib\*\*.nuspec` | Usually no registry entry of its own. |
| Scoop | `$SCOOP\apps\*\current\manifest.json` | Nothing in the registry, nothing in Program Files. |

**winget is deliberately absent.** It's the obvious fifth, and adding it
would be a bug: `winget install` hands off to the program's own MSI or EXE
installer, which writes the same Uninstall key everything else does. Those
apps are already listed under Installer (MSI/EXE). A winget backend would
double-list every one of them, and the second row's "uninstall" would race
the first. There is no separate winget-managed store to enumerate. The
`--source msstore` case is Store packages, also already covered.

The registry is read through `winreg` (standard library) across the 64-bit
view, the 32-bit view (`KEY_WOW64_32KEY`, i.e. `WOW6432Node`) and `HKCU`.
Missing any one of them silently hides a third of a typical machine's
software — 32-bit installers are still extremely common.

Two filters are applied, mirroring `apt-mark showmanual`'s "things the user
chose": entries with a `ParentKeyName` (patches owned by another product) and
entries whose `ReleaseType` is an update/hotfix are dropped. Entries with
`SystemComponent=1` are the opposite case — Windows hides those from Apps &
Features, and surfacing what the built-in tool won't is the entire point of
this project, so they are shown and classified Critical.

## Reading Chocolatey and Scoop off disk instead of calling their CLIs

Same decision as parsing Wine's `system.reg` directly on Linux, for the same
two reasons: it's faster than starting a process per scan, and the file
layout is far more stable than the command line. Chocolatey 2.0 changed what
a bare `choco list` means (it used to search the remote feed; `--local-only`
was then removed), so a CLI-based scan would have silently broken across a
major version. `lib\<pkg>\<pkg>.nuspec` has not moved. Uninstalling still
goes through `choco`/`scoop`, because that's a state change and their own
hooks need to run — only *listing* reads the disk directly.

`.nuspec` tags are matched on local name because the XML namespace varies by
the version of Chocolatey that wrote the file.

## Privilege escalation: `ShellExecuteEx` + `runas`, not `sudo`

CLAUDE.md's non-negotiable, in its Windows form. There is no command you can
prefix to get elevation — UAC is a property of *how a process is launched*,
so `elevate.py` asks the shell to launch it with the `runas` verb via
`ShellExecuteExW`. `ctypes` reaches shell32 with no new dependency, the
consent dialog is the OS's, and no credential ever touches this process.

Three things this forced:

- **`SEE_MASK_NOCLOSEPROCESS` + `WaitForSingleObject`.** Plain
  `ShellExecuteW` returns immediately and tells you nothing. The flow needs
  to know whether the uninstall actually succeeded before it scans for
  leftovers, so the handle is kept and waited on, and the exit code read.
- **Output has to come back through a file.** An elevated child runs at a
  higher integrity level and can't inherit our pipes, so `capture_output`
  returns nothing. The command is wrapped in `cmd /c … > tempfile 2>&1` and
  the file is read back — otherwise every failure message from an elevated
  uninstaller would be lost, and the GUI's "Some items failed" dialog would
  have nothing to show.
- **Elevation is per-item, not per-app.** Scope comes from where the entry
  was found: `HKLM` or `ProgramData` → elevated; `HKCU`, a per-user Store
  package or a user-scope Scoop app → no prompt at all. Exactly the Linux
  split between apt/snap (pkexec) and Flatpak `--user`/Wine (never).

`CREATE_NO_WINDOW` is set on every non-elevated call. This is a `--windowed`
build with no console, so without it each scan would flash console windows
across the screen.

## Output goes to files, not pipes

`elevate.run` used `capture_output=True`, which reads the child's pipes to
EOF — and EOF only arrives when *every* process holding the pipe has exited.
Uninstallers routinely start something on their way out (a browser page
asking why you left, an updater) that inherits those handles, so an
uninstall that had finished sat on "Uninstalling…" for as long as that
process lived — indefinitely, for a browser. Reproduced with a fake
uninstaller that exits at once but leaves a 20 s child: `run()` returned
after 19.3 s; with temp files, 0.1 s. `subprocess.run` with file handles
waits for the uninstaller's own exit and nothing else. The elevated path
already did this (`cmd /c … > file`).

## `split_command` crashed every registry uninstall; workers can't die silently

The first "uninstall never finishes" report (IObit Uninstaller) wasn't the
pipe issue above: the worker thread had died before launching anything.
`CommandLineToArgvW` was called with ctypes' default restype, a C `int`, so
the returned `LPWSTR*` came back as a plain (on 64-bit, truncated) integer
and indexing it raised `TypeError`. The traceback went to stderr of a
`--windowed` app — nowhere — and the GUI waited forever for a callback the
dead thread would never schedule. Found with `py-spy dump` (only the main
thread left) and by reading the process's console buffer.

Two fixes: declare `argtypes`/`restype` (any ctypes call returning a
pointer needs this — the default silently truncates), and the uninstall
worker catches any exception and reports it as that item's failure, so a
future bug shows up as a red bar and a message instead of a hang.
`test_split_command` covers the parser with IObit's real command line.

The next error behind it: `_run_elevated` quoted cmd's whole parameter
string *including* `/c` (`"/c "C:\Program Files\…\unins.exe" /S > "log""`).
cmd's quote-stripping then split the program path at its first space —
`'C:\Program' is not recognized` — and mangled switches even for paths
without spaces, so every machine-wide uninstall failed. The quotes belong
after the switch: `/c "<command> > "log" 2>&1"`, where cmd strips only the
outer pair. Built by the pure `elevated_cmd_params`, and
`test_elevated_cmd_params` runs the result through a real `cmd.exe` with a
`Program Files` path.

## Hand-off uninstallers: follow the process tree, then ask the registry

With the quoting fixed, IObit's uninstall ran — and was reported *failed*
while IObit's own "why are you uninstalling?" prompt was still on screen;
the rescan that followed still listed it, though it was gone moments later.
Inno Setup's `unins000.exe` (like NSIS's `Au_.exe`) copies itself to
%TEMP%, launches the copy and exits. Our wait ended with the launcher.

Two changes, registry uninstalls only (`run(..., follow=True, done=…)`):

- **Wait for the whole process family.** A Toolhelp32 snapshot every 0.5 s
  gives pid → parent pid for every process, elevated ones included, with no
  access rights needed. Parent pids survive the parent's exit, so a
  grandchild launched through an already-dead copy is still traced —
  provided we saw the copy while it lived, hence polling from launch rather
  than looking once at the end. `family_of` is the pure part, tested.
- **"Did it go?" is the registry's call, not the exit code** — the Linux
  build trusting dpkg's status, the Android build asking the package
  manager. A launcher's exit code says nothing about the removal. The same
  check ends the wait early once the Uninstall key is gone, so a browser
  page the uninstaller opens on its way out can't hold the wait open (the
  pipe problem above, in another form). Still registered after a clean
  exit → reported as "still installed — was it cancelled?".

Proven with a fake launcher → middle (exits) → worker (3 s): no follow
returned at 0.2 s; follow waited 3.7 s; follow with `done()` true returned
at the first poll.

Second report, same symptom (IObit Software Updater: "failed", then gone):
tracing needs the launcher seen alive once, and at a 0.5 s poll a launcher
that copies itself and exits in ~100 ms slips between snapshots — the copy's
parent pid then points at a process we never saw. Two fixes: poll every
0.1 s while the launched process lives (0.5 s after), and adopt any
*installer temp copy* — an image named `*.tmp` (Inno's `_iu*.tmp`) or
`Au_.exe`/`Un_A.exe` (NSIS) — that wasn't running before launch (a
snapshot taken just before `ShellExecuteEx`/`Popen`) and whose parent is
gone. Names, not paths: Toolhelp gives the image name for free, and a
full path of an elevated process would need a handle per process. Tested
with python.exe copied to `%TEMP%\_iu_test.tmp`, launched by a parent that
exits at once: the wait lasted the copy's 3 s.

The other way an uninstall looks stuck is legitimate: a program with no
silent uninstall opens its own wizard and waits for clicks, possibly behind
our window. The status line says so ("finish any window it opens") rather
than the app guessing a silent switch — see README.

## Risk heuristic: registry fields, same as the Linux build reads dpkg fields

No extra process per app, for the same scan-speed reason. Windows has no
reverse-dependency database to consult even if speed were free — the nearest
equivalent is scanning every other program's imports, which is not a
scan-time operation. So, off fields the enumeration already returned:
`SystemComponent=1` or `ReleaseType=Driver` or a driver-ish name → Critical;
a redistributable/runtime name (VC++, .NET, WebView2, DirectX, Java) →
Caution; everything else Safe. Appx gets a genuinely authoritative signal
instead of a guess — `IsFramework` is Microsoft's own flag for "a runtime
other packages bind to" — plus a name-pattern check for Windows' own
packages. Chocolatey/Scoop packages are Safe except the managers themselves.

`msiexec /x {GUID} /qn /norestart` is substituted for an MSI's registered
`UninstallString`, because that string is typically `MsiExec.exe /I{GUID}`
and `/I` opens the interactive repair-or-remove dialog rather than
uninstalling. A `QuietUninstallString`, where a program publishes one, wins
over both. A plain EXE uninstaller with no published silent switch is run
as-is and shows its own window: NSIS wants `/S`, Inno wants `/VERYSILENT`,
others want neither, and there is no way to tell which from the registry.
Guessing wrong on an uninstall is worse than an extra click.

Exit code 1605 (`ERROR_UNKNOWN_PRODUCT`) is treated as success for the same
reason the Linux build trusts dpkg's status field over a failing `postrm`'s
exit code: it means the product is already gone, so the files are gone, so
the leftover scan should still run.

## Leftovers: AppData and ProgramData, not Documents and not the registry

`%APPDATA%`, `%LOCALAPPDATA%`, `%LOCALAPPDATA%\..\LocalLow` and
`%ProgramData%`, name-matched exactly like the Linux build's `~/.config` &c.
Two deliberate exclusions:

- **Documents** is where the user's own files live. A name match there could
  offer to delete a folder of someone's work, and the leftover dialog
  pre-checks everything it finds. The asymmetry of that mistake is not worth
  the recall.
- **The registry** is the obvious Windows-specific addition, and it is real
  leftover state that Revo's reputation was built on. It's deferred rather
  than skipped (features.md) because it needs its own confirmation UI: an
  orphaned `HKCU\Software\<Vendor>` key deleted wrongly is not recoverable
  from a Recycle Bin the way a directory is, so it can't just be appended to
  the existing file list.

## Taskbar identity: `SetCurrentProcessExplicitAppUserModelID`

The same trap as the Linux build's `.desktop` app-id mismatch, in Windows
form. The shell groups taskbar buttons and picks their icon by a process's
AppUserModelID, which defaults to the host executable — so a Python GUI
shows Python's icon. Setting it explicitly, *before any window exists*
(Windows caches the decision), makes the taskbar match the app. Paired with
`SetProcessDpiAwareness(1)`, without which the whole UI is scaled up as a
blurry bitmap on any high-DPI display.

## The `.ico` is generated from the same curves, by a stdlib script

Windows needs a multi-size `.ico` for the window, the taskbar, the `.exe`'s
resource and the Apps & Features entry; GTK just scales the `.svg`. The
options were to add a rasterizer (cairosvg, or Pillow which can't read SVG
anyway) as a build dependency, or to hand-draw the icon a second time and let
the two drift. Neither. `windows/tools/make_icon.py` re-evaluates the same
four cubic beziers from `icon.svg`, strokes them as capsules (distance to
segment ≤ radius, which gives the round caps and joins for free),
supersamples 4× and box-filters down, and writes the ICO container itself
with `struct` and `zlib` — DIB entries for the small sizes, PNG for 128 and
256 so the file doesn't carry a quarter-megabyte bitmap. About 150 lines,
no dependency, runs on the Linux development machine. The `.ico` is
committed, so an ordinary build never runs it; re-run it after editing the
SVG.

## Build: PyInstaller for the `.exe`, WiX for the `.msi`, on a Windows runner

Two artifacts because they answer different questions. `Stitches.exe` (named
`TheUninstaller.exe` before the rename) is `--onefile --windowed`: download, double-click, nothing installed —
which is what people actually want from a tool whose job is to clean up
after installers. The `.msi` is the same executable placed in Program Files
with a Start Menu shortcut and an Apps & Features entry, so the uninstaller
can itself be uninstalled the ordinary way. That felt like a hard requirement
for this app in particular.

Rejected: **cx_Freeze**, which can emit both from one tool, because its MSI
support is the weaker half and it produces a directory rather than a single
portable file — the `.exe` is the artifact most people will take.
**Inno Setup / NSIS**, which produce a setup `.exe`, not the `.msi` that
group policy and `msiexec /i /qn` deployment need. The WiX source is ~40
lines for one file, one shortcut and `MajorUpgrade`; a directory-chooser UI
was skipped because there is one file to place.

Neither artifact can be produced on Linux — PyInstaller freezes the
interpreter of the OS it runs on, and WiX needs Windows Installer. So
`.github/workflows/windows-build.yml` is the build machine: it runs the test
suite and the GUI smoke test, builds both, writes `SHA256SUMS.txt`, uploads
them as workflow artifacts, and on a `v*` tag attaches them to that release
with the preinstalled `gh` (no third-party action, no stored token).

## `run.py` exists because a frozen `__main__` isn't a package member

PyInstaller runs the entry script as `__main__`, not as `uninstaller.__main__`,
so the package's relative imports have no package to resolve against and the
build fails at startup. `run.py` is a three-line absolute-import shim. The
`__main__.py` beside it stays for `python -m uninstaller` from a checkout.

## Windows: the Stitches design and tools (0.2.0)

The Windows build now has the Linux window: the dock in the same groups,
the same seven tools, one module per page under `pages/`, and one logic
module per tool beside them (`updates.py`, `cleanup.py`, `drivers.py`,
`defrag.py`, `diagnose.py`, `selfupdate.py`), each with its pure parsing and
verdicts above an `# ---- IO below ----` line, as on Linux. The version went
to 0.2.0 with Linux's. The self-updater compares its own `__version__` with
the release tag, so a Windows build still saying 0.1.0 would offer the same
update on every start.

### How pages are drawn

- **One ticked table.** Updates, Cleanup and Drivers share `widgets.Table`, a
  canvas list like Uninstall's (a Treeview can't colour one cell). A cell is
  a string or a list of parts (text, dim text, a tag), so Cleanup's "reason
  with the risk tag at its end" is one cell. `tickable` decides which rows
  get a tick at all (Drivers: only rows with an update), and `pickable`
  decides what the circle may pick (Uninstall's rule of skipping Critical).
  Uninstall keeps its own canvas: it worked, it's what the smoke test pins
  down, and moving it would be churn. The filter and search pills and
  `fit_text`/`draw_tag` did move into `widgets.py`, and Uninstall uses them.
- **`Page.auto_load`.** Every page scans when the window opens except
  Diagnose, as on Linux.
- **The update notice** is an `ActionBar` placed over the top of the window,
  with `countdown()`: the line starts full and runs down over 4 s. A click
  on its text puts it away. A failure stays up with a red line.

### Running things

- **`elevate.run(on_line=)`** streams a command's lines (stdout and stderr
  together) for Diagnose's Terminal. An elevated command can't stream: its
  output only comes back through the temp file once it ends.
- **Elevated PowerShell goes as `-EncodedCommand`.** `_run_elevated` wraps the
  command in `cmd /c "…"`, and cmd's quoting knows nothing of PowerShell's.
  A script with a pipe, a quote or a `$` breaks there. Base64 of UTF-16 has
  nothing left to quote. Unelevated calls keep `-Command`.
- **`clean_output`.** `sfc` writes UTF-16, so its text arrives with a NUL
  after each letter. `sfc`, `DISM` and `chkdsk` also redraw their progress
  after a bare `\r`. The temp file is read with `newline=""` so those `\r`
  survive, and only the text after the last one on each line is kept.
- **PowerShell output for parsing is tab-separated lines**, not CSV and not
  `ConvertTo-Json`. Titles hold commas and quotes, and JSON of a COM object
  or a CIM instance drags in every property.

### Updates: Windows Update, winget, Chocolatey, Scoop

| Source | Found with | Updated with |
|---|---|---|
| Windows Update | `Microsoft.Update.Session` search, `Type='Software'` (no admin needed) | the same COM API, elevated: search again by UpdateID, download, install |
| winget | `winget upgrade`'s table | `winget upgrade --id … --exact --silent`, one at a time |
| Chocolatey | `choco outdated -r` (pinned ones left out) | `choco upgrade … -y`, elevated, one batch |
| Scoop | `scoop status` | `scoop update …`, one batch, no prompt |

- **winget is a source here, though not on Uninstall.** Listing through it
  would double-list every program the registry already shows. Its upgrade
  feed is different: it's the only thing that knows a newer version of an
  ordinary installer exists, the way a vendor apt repo does on Linux.
- **The winget table is read from the right.** Its headers are translated,
  so they can't be used to find columns. Id, Version, Available and Source
  never contain spaces; Name does, and is cut with "…". `< 1.2` (a version
  winget can't pin down) is re-joined. The table ends at the first blank
  line. winget writes UTF-8 when not on a console, so it's read as UTF-8.
- **`scoop status` columns are cut where the dashes start**, because its
  header names ("Installed Version") have spaces in them.
- **Windows Update ids go into a PowerShell script**, so only hex and dashes
  are let through. A search result can't cross processes, so the elevated
  script searches again and picks by id. It says when Windows wants a
  restart and never restarts by itself.
- Batches follow the Linux rule: one permission prompt per source, not one
  per package. winget installers ask for elevation themselves if they need
  it, so they go one at a time, each with its own progress slice.

### Cleanup

| Location | How | Risk |
|---|---|---|
| Windows Update downloads | elevated: stop `wuauserv`/`bits`, empty `SoftwareDistribution\Download`, start them | Safe |
| Browser caches | Chromium's `Cache`, `Code Cache`, `GPUCache` per profile; Firefox's `cache2` | Safe |
| Shader caches | `D3DSCache`, NVIDIA and AMD shader caches | Safe |
| Crash dumps, error reports | `%LOCALAPPDATA%\CrashDumps`, `…\Microsoft\Windows\WER` | Safe |
| Scoop download cache | `$SCOOP\cache` | Safe |
| Temp files older than a day | `%TEMP%`, per entry; stale all the way down | Caution |
| Recycle Bin | size from `SHQueryRecycleBinW`, emptied with `Clear-RecycleBin` | Caution |

- **Left out on purpose:** thumbnails (`thumbcache_*.db` is always held open
  by Explorer, so the row would fail every time); `C:\Windows\Temp` and
  Delivery Optimization (admin just to measure; features.md); `Prefetch`
  (Windows' own speed-up, not junk).
- Temp needs no socket check: Windows keeps a file a program has open
  locked, and deleting it fails and is logged instead. `is_stale` still
  walks the whole entry, because a setup unpacking into an old folder has
  fresh files inside it.

### Drivers

One place to ask, unlike Linux's three: `Win32_PnPSignedDriver` for the
devices, and Windows Update (`Type='Driver'`) for the updates, which is also
where firmware and UEFI capsules come from. Only the device classes a person
recognises are shown (display, network, audio, storage, Bluetooth,
firmware). Devices Windows made up in software (`ROOT\`, `SWD\`: WAN
miniports, virtual audio) are left out. An update is matched to its device
by `DriverModel` against `DeviceName`; one with no device in the list gets a
row of its own. The new version comes from the update's title ("Intel -
Display - 31.0.101.4502"), since the API has only its date. Vendor tools
(GeForce Experience, Adrenalin) stay the vendors'.

### Defrag

`Optimize-Volume` picks by itself: it defragments a hard disk and sends TRIM
to an SSD. So on Windows an SSD is something to do, not something to skip
as on Linux. Tiles are grouped by disk rather than OS: with drive letters,
everything visible is Windows'. What's left out: file systems `defrag.exe`
won't take (exFAT, none), and USB flash drives, which gain nothing and
wear. All ticked drives go in one elevated script, so there's one prompt,
and each drive's failure is reported while the rest still run.

### Diagnose: the tools themselves, not stand-ins

On Linux each check stands in for a Windows tool. Here the tools are there,
so the "like" line names the tool itself. The Linux rule holds: every check
reads without admin rights.
- **Checks:** drive health (`Get-PhysicalDisk`), file systems
  (`Get-Volume`), free space, failed services, errors since startup
  (`Get-WinEvent`, System and Application logs), a pending restart, the
  quick memory test.
  - Services: auto-start ones that stopped with a non-zero exit code. 1077
    ("never started") is left out: a trigger-start service nothing has
    needed yet.
  - Pending restart: the servicing `RebootPending` and Windows Update
    `RebootRequired` keys. `PendingFileRenameOperations` is ignored: too
    many installers leave it set for good.
- **Fixes you start, not checks:** `sfc` and `DISM` can't even look without
  admin rights, so each is an Info row with a fix.
- **Fixes with no restart:** `chkdsk /scan` (online) instead of Linux's
  check-at-restart. The Windows Memory Diagnostic asks its own "restart now
  or next time", so Stitches doesn't need a second dialog for that.
- **After a fix** the check runs again and its row updates.

### Self-update

The same GitHub check as Linux. How to install depends on where this copy
runs from:
- **`sys.executable` under `%ProgramFiles%`** (the `.msi`'s copy): the new
  `.msi` is downloaded, checked, and opened with `os.startfile`. That is
  what a double-click does, so Windows Installer asks for elevation itself.
  Stitches closes so the installer can replace its exe. The file stays in
  `%TEMP%`, because the installer is still reading it.
- **The portable exe:** a running exe can't be overwritten but can be
  renamed. So it's renamed to `.old`, the new one moved in, and the new one
  started. It's started with `PYINSTALLER_RESET_ENVIRONMENT=1` and without
  `_MEIPASS2`; otherwise a onefile child reuses the parent's unpacked files,
  which vanish when the parent exits. `tidy()` deletes the `.old` on the
  next start.
- **Not frozen:** a checkout, told to `git pull`.

---

# Android port (`android/`)

## A third sibling tree, and the one place the shape breaks

Same reasoning as `windows/`: a parallel tree, not a cross-platform layer.
`Models.kt`, `Risk.kt`, `Leftovers.kt`, `Scanner.kt` and `Uninstaller.kt` are
the same five responsibilities under the same five names, so a reader who
knows either of the other builds knows this one.

The one deliberate break is `backends/`. Linux and Windows each have four
*separate places* software can hide, which is what earns a directory of
backends and a `Backend` protocol over them. Android has exactly one register
of installed software; "Play Store" and "sideloaded APK" are not two places to
look, they are two values of one field on the same row. A `backends/`
directory here would hold one file, and `base.py`'s own comment says why that
would be wrong — no interface for a single implementation. So `Scanner.kt`
does the PackageManager calls directly and `Sources.kt` holds the pure
field-to-tag mapping.

`App` also drops the `extra` map the other two carry. There, an uninstall
needs a Wine prefix or a registry uninstall string to travel with the row.
Here a package name is the whole handle, so the map would always be empty.

## Kotlin, and the platform's own widgets: no AndroidX, no Compose

Third rung of the same ladder. GTK3 was already on every Ubuntu desktop;
tkinter was already in Python on Windows; `android.widget` is already in every
Android device's system image. The app declares **no** Android library
dependencies — no AndroidX, no Material Components, no Compose, no
RecyclerView. `Activity`, `ListView`, `BaseAdapter`, `AlertDialog`,
`ProgressBar` and `@android:style/Theme.Material` are all framework classes
that cost nothing to ship.

The release APK is **57 KB**. A stock Compose or Material-Components app of
the same scope is comfortably two orders of magnitude larger, essentially all
of it a UI toolkit being redistributed to a device that already has one. For
a tool whose pitch is cleaning junk off your phone, that number is part of the
argument.

Kotlin rather than Java, despite Java needing no Gradle plugin: the data
classes, enums with fields, and `when` expressions map one-to-one onto the
Python `dataclass`/`Enum`/early-return structure the other two builds use, so
the shared shape survives. In Java the same five files would be roughly twice
the length and would stop looking like their siblings.

What the no-library choice costs, and what was done about it:

- **No `RecyclerView`.** `ListView` + `BaseAdapter` with the standard
  `convertView` recycling. Marked as fine at this scale — a phone has a few
  hundred packages, not a few hundred thousand.
- **No `ActivityResultLauncher`.** The uninstall flow uses
  `startActivityForResult`/`onActivityResult`, which are deprecated but are
  framework methods; the replacement lives in AndroidX and would be the
  app's only reason to depend on it.
- **No `DayNight` theme with automatic following.** Two platform Material
  themes and `recreate()` on toggle, matching the Linux and Windows builds'
  explicit 🌙/☀ control. The risk colours are picked to read on both
  surfaces, so unlike the Windows build there's only one palette. (The
  Stitches design made that four themes, and first run follows the system;
  see "The Stitches design" below.)

## The gap here is a different shape, and the docs say so

On Linux the app store genuinely cannot see a `.deb` you installed; on Windows
Apps & Features genuinely cannot see Scoop. Android Settings *does* list every
installed app, so claiming otherwise would be marketing. What it doesn't do:
say where any app came from (you'd open each app's page and scroll), remove
more than one at a time, warn you that the thing you're removing is your
keyboard, or clean up the folder an app left at the top of your storage. That
is the honest pitch and it's what `android/README.md` leads with.

## Five sources out of one field

`PackageManager.getInstallSourceInfo()` (`getInstallerPackageName()` below
API 30) returns the package that performed the install, and every tag is
derived from it:

| Source | Installing package |
|---|---|
| Play Store | `com.android.vending` |
| F-Droid | `org.fdroid.fdroid` and friends |
| Other app store | anything else that isn't a system installer |
| Sideloaded APK | the system installer UI, `com.android.shell`, or nothing |
| Preinstalled | — decided by `FLAG_SYSTEM`, which wins over the installer |

Two decisions worth keeping:

- **An unrecognised installer is a store, not a sideload.** The naive
  mapping — a known list, everything else "sideloaded" — would mislabel every
  vendor store on the market, and the list of those is unbounded. So the
  fallback is `OTHER_STORE` and the installing package name is shown
  verbatim, which degrades into useful information instead of a wrong tag.
- **`FLAG_SYSTEM` wins.** A preinstalled app sometimes carries Play as its
  installer because Play updated it. "It shipped with the device" is the fact
  that decides what can be done with it, so it takes precedence.

`winget`'s absence has no analogue here: there is no second register that
would double-list anything.

## Privilege escalation: the system's own uninstall dialog

CLAUDE.md's non-negotiable, in its Android form, and the one platform where it
costs no code at all. There is no API for a normal app to remove another app.
`Intent.ACTION_DELETE` asks the system to do it, and the system draws its own
confirmation under its own identity. `pkexec` and `ShellExecuteEx`/`runas`
were both work; here the rail is the only thing that exists.

It also sets a hard limit the UI has to be honest about: **one dialog per
app**. There is no batch uninstall for an unprivileged app, so bulk selection
means a queue — `nextRemoval()` launches one, `onActivityResult` records the
outcome and launches the next. A device-owner or Shizuku path could do it
silently; that's a different trust model, and it's in features.md as future
work rather than something to fake.

## "Did it go?" is asked of the package manager, not the result code

The same lesson both earlier builds learned, arrived at a third time. The
Linux build stopped trusting a failing `postrm`'s exit code and started
reading dpkg's status field; the Windows build treats MSI 1605 as success
because it means the product is already gone. Here `resultCode` is ignored
outright: it reports what the dialog returned, and
`getApplicationInfo(…, MATCH_DISABLED_COMPONENTS)` reports what is true.

Reading it through `MATCH_DISABLED_COMPONENTS` rather than letting the lookup
throw is deliberate — it makes *disabled* a distinguishable third outcome
rather than being indistinguishable from "still installed", which is what the
preinstalled-app path needs.

## Preinstalled apps get App Info, because Disable is the only real verb

Selecting a preinstalled app doesn't fire `ACTION_DELETE`; it opens
`ACTION_APPLICATION_DETAILS_SETTINGS`, which is where **Disable** and
**Uninstall updates** live. Those are the only two things Android permits, and
`ACTION_DELETE` on a system app either silently removes just the update or
does nothing at all, which would make the result dialog lie.

Two follow-ons: the outcome is reported as "Disabled — Android won't fully
remove a preinstalled app" rather than "Removed", and a disabled app's size is
**excluded from the space-freed total**. It's still on the partition. That
matters because "freed X" is a number the other two builds worked to get
right, and inflating it here would be the easy wrong answer.

## Risk heuristic: three authoritative signals, one name pattern

Same constraint as always — no extra process or query per app, and no reverse
dependency graph to consult. But Android gives better raw material than
either earlier platform, and three of the signals are facts rather than
guesses:

- the default launcher — `resolveActivity` on `CATEGORY_HOME`
- active device admins — `DevicePolicyManager.activeAdmins`
- the active keyboard — `Settings.Secure.DEFAULT_INPUT_METHOD`

Each is **one query per scan**, not per app, which is what makes them
affordable. All three are Critical: removing your home screen leaves a device
with no way to open anything, and Android will refuse a device admin's
removal outright.

Below them, a fourth free signal: **no launcher entry** (from one
`queryIntentActivities` call) means an app the user never opens directly — a
plugin, a provider, a background service something else is bound to — which
is Caution.

The only guess left is splitting core Android from vendor preinstalls by
package-name pattern (`com.android.*`, `com.google.android.gms`, and so on).
That split is what makes the preinstalled rating useful rather than uniform:
core platform packages are Critical, and the shopping app your manufacturer
preloaded is Caution — preinstalled, so not auto-selectable, but honestly
described as disable-able rather than dangerous.

## Leftovers: shared storage only, and never the media folders

Android already removes `/data/data/<pkg>` and the app's own `Android/data`
and `Android/obb` directories on uninstall, so unlike apt or a Windows
installer it does most of the job. What survives is the folder an app made for
itself at the top of shared storage, which nothing ever cleans up. So the
roots are the storage root, `Download`, `Android/data` and `Android/obb`.

Match terms are the display name, the package name, **and the package's last
segment** (`com.acme.coolapp` → `coolapp`), which is what an app most often
names its own folder after. Same three-character minimum as the other builds.

`DCIM`, `Pictures`, `Music`, `Movies`, `Documents`, `Ringtones` and the rest
are excluded, for exactly the reason the Windows build skips `Documents`: the
leftover dialog pre-checks what it finds, and a name collision there could
offer to delete someone's photos. The asymmetry of that mistake is not worth
the recall. Splitting the results by confidence — an exact package-name folder
is certain, a fuzzy top-level match is a guess — is in features.md as the
next improvement.

## Two optional permissions, both skippable, neither assumed

`MANAGE_EXTERNAL_STORAGE` (leftover scanning) and `PACKAGE_USAGE_STATS` (real
app sizes) are both "special access" permissions: they cannot be requested
with a runtime dialog, only by sending the user to a Settings screen. So
neither is treated as a precondition.

Without all-files access the leftover scan finds nothing —
`File.listFiles()` returns null and the code reads that as "no leftovers"
rather than failing. Without usage access, size falls back to
`File(sourceDir).length()`, the APK's own size, which under-reports exactly
the apps worth removing (a small app with a 2 GB data directory). A dismissible
banner says which one is missing and what it would buy; the app is fully
usable ignoring it.

## `QUERY_ALL_PACKAGES` is why the artifact is an APK

On API 30+ an app sees only packages it declared in `<queries>` unless it
holds `QUERY_ALL_PACKAGES`. Listing what's installed is the entire product, so
a declared `<queries>` list is not an option — it would mean knowing every app
worth listing in advance.

Google Play restricts that permission to a short list of approved app
categories, and the honest position is that this app might not clear that bar.
Rather than design around a review outcome, the release artifact is a signed
APK on GitHub Releases, same as the Windows `.exe`. A Play-flavoured build
with a declared query list is in features.md as a separate thing, because it
would be a materially less useful app.

## Health check: what an app can see, and nothing it can't

The Linux Diagnose page's Android counterpart was a menu item and one dialog,
not a new screen; the Stitches design made it the Home page (below). Scanning system files, testing RAM and reading the storage
chip's wear all need root on Android, so they're absent rather than faked,
and the dialog says so. Android's own answer to `sfc /scannow` is verified
boot, so `ro.boot.verifiedbootstate` (green / yellow / orange) leads the
list; it's read with `getprop` because `SystemProperties` is hidden API, and
some devices refuse even that, which shows as "Info". The rest are public
APIs: `StatFs`, `ActivityManager.MemoryInfo`, the sticky
`ACTION_BATTERY_CHANGED` broadcast, `PowerManager.currentThermalStatus`
(API 29+), `SECURITY_PATCH` (parsed with `SimpleDateFormat`, since
`java.time` needs API 26 and the app supports 24), `KeyguardManager`,
`DevicePolicyManager.storageEncryptionStatus`, the developer-options and ADB
settings, and an `su` binary on the usual paths. Each verdict is a pure
function in `Health.kt` over plain values, tested on the JVM like everything
else here. The APK grew from 57 to about 60 KB (85 KB after the Stitches
design).

## The icon is the same path data, not a second drawing (until it was sewn)

*Superseded by "The sewn logo needs a generator" below; kept for why the
first icon had no script.*

Android vector drawables take SVG path data verbatim in `android:pathData`,
and support `strokeWidth`/`strokeLineCap`, so the two curves from
`linux/src/uninstaller/icon.svg` are copied across as-is inside a `<group>` that
scales the 100×100 viewBox into the 108×108 adaptive-icon canvas. No
rasteriser, no generator script, and no committed bitmaps — this is the one
place Android is *simpler* than the Windows build, which needed 150 lines of
`make_icon.py` to produce a multi-size `.ico`.

API 24–25 predates adaptive icons, so `mipmap-anydpi/ic_launcher.xml` holds
the whole thing including the rounded background rect, and
`mipmap-anydpi-v26/` holds the adaptive version. Two small XML files instead
of five densities of PNG.

## Build: Gradle and R8 on any machine, and a key that has to exist

Unlike the Windows build, nothing here needs a special runner — the Android
toolchain is cross-platform and the APK was built and signed on the Linux
development machine. `android-build.yml` exists for the *key*, not the
platform: a release APK must be signed, Android only accepts updates signed
with the same key, and that key belongs in repository secrets rather than on
a laptop. The workflow fails a tag build outright if the secret is missing,
because an unsigned or throwaway-signed release is worse than no release.

`build-apk.sh` generates a local `keystore.jks` on first run instead of
emitting an unsigned APK, since an unsigned APK cannot be installed and would
be a build that produces nothing usable. It and `keystore.properties` are
gitignored, and the script says plainly that the file has to be kept.

R8 shrinking and resource shrinking are on, with an **empty**
`proguard-rules.pro`: the app has no reflection, no serialization library and
no JNI, so the defaults are correct and a keep rule would be cargo cult. That
empty file with a comment explaining why is the honest artifact.

## The Stitches design

Asked to make the Android app look like Stitches on Linux. It still uses
only framework widgets (no AndroidX, no Material Components), so the
design is layouts, shape and vector drawables, and one small span.

**Structure, as on Linux.** `MainActivity` is the window: a `FrameLayout`
holding both pages, and a dock under it. The Linux `pages/` split is kept:
`HomePage.kt` and `UninstallPage.kt` each own one page's views, and `Ui.kt`
plays `widgets.py`'s part (the tag, the action bar). The ⋮ menu is gone:
- the logo is Home and opens first, as on Linux;
- Uninstall is its own dock button;
- theme and optional access sit at the dock's end;
- refresh is the ↻ in each page header.

The page index survives the `recreate()` a theme change needs, through
`onSaveInstanceState`. Removal still runs through the Activity's
`startActivityForResult`, and `onActivityResult` hands it to the page.

**Home is the Health check.** On Linux, Home says what the machine is and
how it's doing, and Diagnose checks and fixes. Android lets an app read the
same kind of facts but fix none of them, so one page holds both. It's laid
out like Linux Home: borderless groups, an accent icon by each heading.
- **This phone:** `Build` model, release and API, `Build.DISPLAY`, and the
  kernel from `os.version`.
- **How it's doing:** storage, memory, battery, temperature.
- **Security:** the rest of the findings.

The split is by finding title in the page (`DOING`), not a field on
`Finding`: it's layout, and `Health.kt` stays about verdicts. Everything is
a system value, so the page reads it all again on every `onResume`.

**Tags.** `TagSpan` is a `ReplacementSpan` that draws a rounded label at
82% of the text size, in the Linux build's colours. That works inline: the
source tag after an app's name, the risk tag at the end of its reason, as
in Linux Cleanup. Its `getSize` must fill in the `FontMetricsInt` it's
handed. A line that is *only* a tag (Home's verdicts) otherwise measures 0
tall and vanishes, because `TextLine` takes the line's height from the
spans when nothing else on the line gives one.

**Select-all circle.** An `ImageView` over the list, drawn empty, dashed or
ticked from `ticked()`, a pure function with a JVM test.
- It ticks every app shown that `bulkPickable()` allows. That's never a
  Critical or preinstalled app, as before.
- When nothing is left to add, it clears what's shown instead. Otherwise an
  app ticked by hand among Critical rows could never be cleared with it.
- Nothing is ticked at first, as before.

**Line loader.** A 3 dp horizontal `ProgressBar` with a layer-list trough:
indeterminate while scanning, filled per app while removing, tinted
`line_error` after the first failure.

**Themes.** Light, Dark, AMOLED and Glass, as on Linux:
- The surfaces are theme attributes (`cardColor`, `cardBorder`,
  `dockColor`, `dockBorder`), which the shape drawables read. One `card.xml`
  serves all four themes.
- **Glass** is `windowShowWallpaper` with a translucent window background:
  translucency without blur, as on Linux.
- The dock follows the window theme. The separate dock theme is a desktop
  nicety, and one choice is enough on a phone.
- The old boolean `dark` preference is still read when no `theme` is set,
  so an upgraded install keeps its look. A fresh one follows the system's
  night mode.
- Parents are `Theme.DeviceDefault`, not `Theme.Material`. It's still the
  platform's own theme, but dialogs come out in the phone's current style
  (rounded) instead of 2014's square grey.

**Verified on an emulator** (API 35, headless, software GPU): all four
themes, both pages, the circle's three states, the confirm dialog's
Critical lock. On the emulator's software renderer, Glass left ghosts of
old text where views redrew. With `debug.hwui.use_partial_updates false`
they went, so it's that renderer's partial updates, not the app. A real
phone should be checked once.

## The sewn logo needs a generator

The Linux logo is now sewn: dashed thread over a seam line, with a running
stitch round the edge. Vector drawables take SVG path data, but have no
`stroke-dasharray`. `android/tools/make_logo.py` (stdlib only, like
Windows' `make_icon.py`) samples each curve and cuts every dash into its own
polyline, simplified with Ramer–Douglas–Peucker. Each dash starts at the
path's start, as SVG's do, so the stitches land where they do on Linux:
checked by drawing both side by side. It writes two files:
- **`drawable/logo.xml`:** the whole tile. It's the dock's Home button,
  and via a one-line `<inset>` in `mipmap-anydpi/`, the API 24–25 launcher
  icon.
- **`drawable/ic_launcher_foreground.xml`:** seam and thread only. An
  adaptive icon's mask would cut the square border stitch at its corners.

No monochrome (themed) icon yet: in one colour, the seam line would join
the stitches into a solid stroke.
