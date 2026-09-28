# Stitches for Windows

The Windows build of [Stitches](../README.md). Same idea as the Linux
one, pointed at a different problem: Apps & Features lists what an MSI or EXE
installer registered, and nothing else. Microsoft Store apps live in a
separate list. Anything you installed with `choco install` or `scoop install`
isn't in either — Scoop in particular puts nothing in the registry at all, so
as far as Windows is concerned those programs don't exist.

This is one list for all of it — tagged by how it got onto your PC, tagged
Safe/Caution/Critical to remove in plain language, with bulk uninstall and
leftover-file cleanup.

## What it detects

| Tag | What it means |
|---|---|
| **Installer (MSI/EXE)** | A normal installer wrote an entry to the registry's Uninstall key — including everything `winget install` puts there. |
| **Microsoft Store** | An MSIX/Appx package. |
| **Chocolatey** | `choco install`. |
| **Scoop** | `scoop install` — invisible to Apps & Features. |

Each item is also rated:

- 🟢 **Safe** — a standalone app; removing it only removes that app.
- 🟡 **Caution** — a shared runtime other programs are built against; read the
  reason shown before removing.
- 🔴 **Critical** — a driver, a Windows framework package, or something
  Windows deliberately hides from Apps & Features (tagged **System**); never
  pre-selected by "Select All".

Design decisions and why:
[../documents/ai-knowledgebase.md](../documents/ai-knowledgebase.md).

## Installation

**Requirements:** Windows 10 or 11.

Pick one:

- **`Stitches-0.1.0-x64.msi`** — installs to `Program Files`, adds a
  Start Menu shortcut, and shows up in Apps & Features so it can be removed
  the ordinary way. Recommended.
- **`Stitches.exe`** — one portable file. Download, double-click, done.
  Nothing is installed and nothing is left behind.

Neither needs Python: the interpreter is inside the executable.

**Running from a checkout instead** (needs Python 3.10+, which already
includes tkinter):

```powershell
$env:PYTHONPATH = "src"; python -m uninstaller
```

### First run

The app only scans (read-only) until you check items and click **Uninstall
Selected**, which always shows a confirmation first. Removing anything
installed for the whole machine raises Windows' standard permission prompt —
this app never asks for credentials itself, and never stores any.

A progress bar and "Scanning for installed software…" show while it's finding
apps; uninstalling shows a per-item bar (green on success, red on failure)
naming the app currently being removed. The 🌙/☀ button switches light/dark.

Programs that publish a silent uninstall command get removed without further
clicks. Those that don't will open their own uninstaller window for you to
click through — there's no reliable way to guess a given installer's silent
switch, and guessing wrong on an uninstall is not a good trade.

## Build

Both artifacts, from a clean checkout on a Windows machine with Python 3.10+
and the .NET SDK:

```powershell
.\build-all.ps1
```

That produces `dist\Stitches.exe`, `dist\Stitches-0.1.0-x64.msi`
and `dist\SHA256SUMS.txt`. The two halves also run on their own
(`.\build-exe.ps1`, `.\build-msi.ps1`). PyInstaller and WiX are installed by
the scripts if they're missing; they're build-time only, and the app itself
imports nothing outside the standard library.

**No Windows machine?** Push a `v*` tag, or run **Windows build** from the
repo's Actions tab: [.github/workflows/windows-build.yml](../.github/workflows/windows-build.yml)
builds both on a Windows runner, uploads them as artifacts, and attaches them
to the tagged release.

The app icon is generated, not hand-drawn twice —
`python tools\make_icon.py` redraws `src\uninstaller\icon.ico` from the same
curves as the Linux build's `icon.svg`, using only the standard library. The
`.ico` is committed, so a normal build never needs to run it.

## Test

```powershell
python tests\test_core.py       # parsers + risk classifier, runs on any OS
python tests\test_gui_smoke.py  # builds the real window; skips with no display
```

`test_core.py` covers every parser (registry entries, Appx CSV, Chocolatey
`.nuspec`, Scoop manifests) and the risk classifier with plain asserts — no
Windows and no particular installed software required, which is why it runs
in the same suite on the Linux development machine.

## Safety notes

- Uninstalling always shows a confirmation listing exactly what's selected
  and its risk level; Critical/System items require an extra explicit
  checkbox before the Uninstall button unlocks.
- "Select All" never selects Critical/System items — pick those one at a
  time if you really mean it.
- Leftover files are shown and opt-in before deletion, never removed
  silently. Only `AppData` and `ProgramData` are scanned: not Documents, and
  not the registry (see the knowledge base for why).
