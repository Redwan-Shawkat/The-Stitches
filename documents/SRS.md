# Software Requirements Specification — Linux the Uninstaller

Version 0.1 · Source of truth for scope. Export to PDF with:
`pandoc documents/SRS.md -o documents/SRS.pdf` (see README for install).

## 1. Purpose

Windows has a mature ecosystem of third-party uninstallers (Revo, IObit,
Geek Uninstaller) that find software regardless of how it was installed and
scrub leftovers behind it. Ubuntu/Debian-based Linux has no equivalent: the
built-in app store (GNOME Software / Ubuntu Software) only manages what it
installed itself. Software installed via `apt`/`dpkg -i`/a downloaded `.deb`,
via Snap or Flatpak outside the store UI, or Windows software run through
Wine, is invisible to it. This product is a single place to see and remove
all of it.

## 2. Scope

In scope:
- Detect installed software from four sources: APT/dpkg (covers terminal
  installs and manually downloaded `.deb` files), Snap, Flatpak, and Wine
  (Windows apps installed into a Wine prefix).
- Tag each item with how it got there.
- Tag system-critical items separately from user-installed apps.
- Classify each item Safe / Caution / Critical to remove, in plain language.
- Uninstall one item, or many at once (bulk).
- After uninstall, find and offer to delete leftover files (config/cache/data
  directories the package manager doesn't own).

Out of scope (v0.1): Windows-registry-style "installed programs" for
native Linux binaries dropped outside a package manager entirely (e.g. a
bare executable in `~/bin` with no manifest — there's no registry to read);
non-Debian distros (Fedora/Arch have different tooling, see
[ai-knowledgebase.md](ai-knowledgebase.md)); telemetry; auto-update.

## 3. Users

A desktop Linux user, not necessarily a terminal expert, who has accumulated
software from several sources over time and wants disk space back or a
clean system, without accidentally breaking it.

## 4. Functional requirements

| # | Requirement |
|---|---|
| FR1 | Scan and list all manually-installed APT/dpkg packages, all Snap packages, all Flatpak apps, and all apps found in Wine prefixes on the system. |
| FR2 | Each row shows: name, source tag (Terminal/apt, Snap Store, Flatpak, Wine, System), version, approximate size, risk tag. |
| FR3 | User can select one or many rows and uninstall them in one action. |
| FR4 | Before uninstalling, show a confirmation listing exactly what will be removed and its risk level. |
| FR5 | After a package-manager uninstall completes, scan common per-user leftover locations for that app's name and offer to delete them (opt-in, shown before deleting). |
| FR6 | System-critical software (OS-essential packages, desktop environment components, Wine/Snap runtime bases) is tagged System and defaults to Critical risk; the UI never bulk-selects these silently. |
| FR7 | Risk tag is explained in one plain-language sentence per item (not just a color). |
| FR8 | Any action needing root (removing an apt/snap package) prompts for authorization via the desktop's standard privilege dialog (`pkexec`) — never stores or asks for a password itself. |
| FR9 | Filter/search the list by name or by source tag. |

## 5. Non-functional requirements

- **Safety first**: destructive actions are never silent or irreversible
  without confirmation; System/Critical items require an extra explicit
  confirmation step.
- **No new system dependencies beyond what a stock Ubuntu desktop already
  ships** (Python 3, PyGObject/GTK3, `dpkg`, `apt`, `snap`, `flatpak`, `wine`
  if the user has it, `pkexec`).
- **Fast scan**: initial list appears in a few seconds on a typical desktop
  install (low hundreds of packages); heavy per-package analysis (e.g. full
  dependency graphs) is avoided in favor of fast heuristics — see
  [ai-knowledgebase.md](ai-knowledgebase.md) for the tradeoff.
- **Transparent**: every uninstall/delete action is one of the standard
  underlying commands (`apt remove`, `snap remove`, `flatpak uninstall`,
  running the app's own Wine uninstaller, or `rm` on a shown leftover path)
  — nothing hidden.

## 6. Risk classification (plain words)

- **Safe** — a standalone app nothing else depends on. Removing it only
  removes that app.
- **Caution** — other apps, your desktop, or your files may depend on this
  (e.g. a shared runtime, a codec library, a browser used to log into
  things). Read the reason shown before removing.
- **Critical** — a core part of the operating system or desktop environment
  (marked `Essential`/`Required`/`Important` by the package system, or a
  Wine/Snap runtime base). Removing it can break your system. Tagged
  **System** and never pre-selected by "select all".

## 7. Out-of-scope distros

Detection backends are Debian/Ubuntu-specific (`dpkg`, `apt-mark`). Snap and
Flatpak backends are distro-agnostic and work anywhere those tools are
installed. See [ai-knowledgebase.md](ai-knowledgebase.md) for the extension
point if RPM-based support is ever wanted.
