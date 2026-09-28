"""Cache and temp cleanup: what can be reclaimed, where it lives, and removing
it. Every location carries the paths or the PowerShell it acts on so the GUI
can show exactly what goes, and nothing here runs until the GUI has asked
(CLAUDE.md non-negotiable). See ai-knowledgebase.md ("Windows: Cleanup")."""

import ctypes
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .backends.scoop_backend import install_roots
from .elevate import powershell
from .leftovers import delete_paths, path_size
from .models import Risk

_DAY = 86400
# Where Chromium browsers keep each profile's caches, under %LOCALAPPDATA%.
_CHROMIUM = ("Microsoft/Edge", "Google/Chrome", "BraveSoftware/Brave-Browser", "Vivaldi")
_SHADER_CACHES = ("D3DSCache", "NVIDIA/DXCache", "NVIDIA/GLCache", "AMD/DxCache", "AMD/DxcCache")


@dataclass
class Location:
    name: str
    where: str  # the folder or command, shown beside the name
    risk: Risk
    reason: str
    items: list[tuple[str, int]]  # (what, bytes): one removal-log line each
    script: str = ""  # PowerShell to run; empty = delete `items` as paths
    admin: bool = False  # asks Windows for permission

    @property
    def size_bytes(self) -> int:
        return sum(size for _, size in self.items)


def is_stale(path: Path, cutoff: float) -> bool:
    """A temp entry nothing has touched since `cutoff`, all the way down: a
    folder a running setup is still unpacking into has fresh files inside."""
    try:
        tree = path.rglob("*") if path.is_dir() and not path.is_symlink() else ()
        return all(entry.lstat().st_mtime <= cutoff for entry in (path, *tree))
    except OSError:
        return False


def browser_caches(local: Path) -> list[Path]:
    """Each browser profile's cache folders: Chromium's per profile under
    User Data, Firefox's cache2 per profile. Bookmarks, passwords and history
    live beside them and aren't touched."""
    found = []
    for browser in _CHROMIUM:
        for name in ("Cache", "Code Cache", "GPUCache"):
            found += sorted((local / browser / "User Data").glob(f"*/{name}"))
    found += sorted((local / "Mozilla/Firefox/Profiles").glob("*/cache2"))
    return [p for p in found if p.is_dir()]


# ---- IO below ----


def _children(folder: Path) -> list[tuple[str, int]]:
    try:
        return [(str(p), path_size(p)) for p in sorted(folder.iterdir())]
    except OSError:
        return []


def _one(label: str, size: int) -> list[tuple[str, int]]:
    return [(label, size)] if size else []


def _update_cache() -> Location:
    folder = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "SoftwareDistribution" / "Download"
    return Location("Windows Update downloads", str(folder), Risk.SAFE,
                    "Installers Windows Update already used. Updates stay installed; Windows downloads one again "
                    "if it needs it.",
                    _one(str(folder), path_size(folder)),
                    # The update service holds files in there while it runs.
                    "Stop-Service wuauserv, bits -Force\n"
                    f"Remove-Item '{folder}\\*' -Recurse -Force -ErrorAction SilentlyContinue\n"
                    "Start-Service wuauserv, bits", admin=True)


def _temp(now: float) -> Location:
    temp, cutoff = Path(os.environ.get("TEMP") or Path.home() / "AppData/Local/Temp"), now - _DAY
    try:
        entries = sorted(temp.iterdir())
    except OSError:
        entries = []
    return Location("Temp files older than a day", str(temp), Risk.CAUTION,
                    "Only yours, untouched for a day, but a program may still expect one. Files a program has "
                    "open can't be removed and are skipped.",
                    [(str(p), path_size(p)) for p in entries if is_stale(p, cutoff)])


def _recycle_bin_size() -> int:
    class _Info(ctypes.Structure):  # SHQUERYRBINFO
        _fields_ = [("cbSize", ctypes.c_uint32), ("i64Size", ctypes.c_int64), ("i64NumItems", ctypes.c_int64)]

    info = _Info(cbSize=ctypes.sizeof(_Info))
    if sys.platform != "win32" or ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) != 0:
        return 0
    return info.i64Size


def scan() -> list[Location]:
    """Every location with something in it."""
    local, now = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local"), time.time()
    makers = (
        _update_cache,
        lambda: Location("Browser caches", "Edge, Chrome, Brave, Vivaldi, Firefox", Risk.SAFE,
                         "Web pages browsers keep to load faster. Not your bookmarks, passwords or history. Close "
                         "the browser first, or what it has open is skipped.",
                         [(str(p), path_size(p)) for p in browser_caches(local)]),
        lambda: Location("Shader caches", str(local / "D3DSCache"), Risk.SAFE,
                         "Graphics code games and apps compiled for your GPU. They build it again; a game may "
                         "stutter briefly the first time.",
                         [item for folder in _SHADER_CACHES for item in _children(local / folder)]),
        lambda: Location("Crash dumps", str(local / "CrashDumps"), Risk.SAFE,
                         "Memory snapshots written when an app crashed. Only a developer debugging that crash "
                         "needs them.", _children(local / "CrashDumps")),
        lambda: Location("Error reports", str(local / "Microsoft/Windows/WER"), Risk.SAFE,
                         "Problem reports Windows kept after sending them, or instead of sending them.",
                         _children(local / "Microsoft/Windows/WER")),
        lambda: Location("Scoop download cache", str(install_roots()[0][0] / "cache"), Risk.SAFE,
                         "Installers Scoop already used. Every app stays installed.",
                         _children(install_roots()[0][0] / "cache")),
        lambda: _temp(now),
        lambda: Location("Recycle Bin", "Clear-RecycleBin", Risk.CAUTION,
                         "Files you deleted, kept until now. This is your own data: nothing can be restored after "
                         "this.", _one("Recycle Bin, every drive", _recycle_bin_size()),
                         "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"),
    )
    found = []
    for make in makers:
        try:
            location = make()
        except OSError:
            continue
        if location.items:
            found.append(location)
    return found


def clean(location: Location, log) -> int:
    """Removes one location, calling log(what, bytes_freed, error_or_None) for
    each line of it. Returns bytes freed."""
    if location.script:
        code, text = powershell(location.script, elevated=location.admin)
        if code != 0:
            log(location.where, 0, (text.splitlines() or ["failed"])[-1])
            return 0
        for what, size in location.items:
            log(what, size, None)
        return location.size_bytes
    freed = 0
    for what, _ in location.items:
        size, errors = delete_paths([Path(what)])
        freed += size
        log(what, size, errors[0][1] if errors else None)
    return freed
