# Stitches for Windows

The Windows build of [Stitches](../README.md). Same idea as the Linux
one, pointed at a different problem: Apps & Features lists what an MSI or EXE
installer registered, and nothing else. Microsoft Store apps live in a
separate list. Anything you installed with `choco install` or `scoop install`
isn't in either — Scoop in particular puts nothing in the registry at all, so
as far as Windows is concerned those programs don't exist.

This is one list for all of it — tagged by how it got onto your PC, tagged
Safe/Caution/Critical to remove in plain language, with bulk uninstall and
leftover-file cleanup. Around it are the same tools as the Linux build, in a
dock along the bottom:

| Tool | What it does |
|---|---|
| **Home** | What the PC is, its BIOS/UEFI settings explained in words (Secure Boot, TPM, virtualization, boot mode, BIOS age), memory use and how full every drive is. |
| **Diagnose** | Windows' own health tools behind one **Scan**: drive health, file-system state (`chkdsk`), free space, failed services, errors since startup (Event Viewer), a restart Windows is waiting for, and a memory test that needs no restart — with a Terminal showing each command. `sfc /scannow`, `DISM /RestoreHealth` and the Windows Memory Diagnostic are a button each; they say what will happen first. |
| **Cleanup** | Windows Update downloads, browser and shader caches, crash dumps, error reports, Scoop's download cache, temp files a day old and the Recycle Bin — each saying where it lives, what removing it means and how risky that is. |
| **Updates** | Pending updates from Windows Update, winget, Chocolatey and Scoop in one list. Windows Update and Chocolatey go as one batch each, so a bulk update asks for permission once per source. |
| **Uninstall** | The list described above. |
| **Drivers** | Display, network, audio, storage, Bluetooth and firmware devices, the driver each runs on and when it was released, and the driver updates Windows Update offers. |
| **Defrag** | Every drive letter as a tile, grouped by disk. Hard disks get defragmented, SSDs trimmed, through Windows' own `Optimize-Volume`. |

The last two dock buttons pick the theme (Light, Dark, AMOLED, Glass) and
update Stitches itself: it checks GitHub for a newer release when it starts.

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

- **`Stitches-0.2.0-x64.msi`** — installs to `Program Files`, adds a
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

Every page but Diagnose scans (read-only) as soon as the window opens, and
nothing changes until you tick items (nothing starts ticked; the circle at
the top of the ticks selects them all) and press the button in the dark bar
at the bottom. Uninstall and Cleanup always show a confirmation first.
Anything that touches the whole machine — removing a machine-wide program,
Windows Update, Chocolatey, drivers, defragmenting, `sfc` and `DISM` — raises
Windows' standard permission prompt; this app never asks for credentials
itself, and never stores any.

While a page works, a thin line runs along the top of its bar: sweeping
while scanning, filling up while working, and turning red if something
fails.

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

That produces `dist\Stitches.exe`, `dist\Stitches-0.2.0-x64.msi`
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
`.nuspec`, Scoop manifests, `winget upgrade`'s table, `choco outdated`,
`scoop status`, Windows Update's answers, device and drive lists), the risk
classifier, the Diagnose verdicts and the self-update choices with plain asserts — no
Windows and no particular installed software required, which is why it runs
in the same suite on the Linux development machine.

## Safety notes

- Uninstalling always shows a confirmation listing exactly what's selected
  and its risk level; Critical/System items require an extra explicit
  checkbox before the Uninstall button unlocks.
- The select-all circle never selects Critical/System items — pick those one
  at a time if you really mean it.
- Cleanup never touches your files or installed apps. The Recycle Bin (files
  you already deleted) is the one exception, and it's rated Caution. Temp
  files are only your own and a day old; one a program has open is skipped.
- A self-update is downloaded first and only put in place once its size, and
  GitHub's checksum when it publishes one, match.
- Leftover files are shown and opt-in before deletion, never removed
  silently. Only `AppData` and `ProgramData` are scanned: not Documents, and
  not the registry (see the knowledge base for why).
