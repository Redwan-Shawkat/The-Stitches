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

# Windows port (`windows/`)

## A sibling tree, not one cross-platform package

`windows/` is a parallel copy of the project, not a `if sys.platform` layer
inside `linux/src/uninstaller`. The two builds share the *shape* — `models.py`,
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

Two artifacts because they answer different questions. `TheUninstaller.exe`
is `--onefile --windowed`: download, double-click, nothing installed —
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
  surfaces, so unlike the Windows build there's only one palette.

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

## The icon is the same path data, not a second drawing

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
