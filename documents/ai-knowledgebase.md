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
