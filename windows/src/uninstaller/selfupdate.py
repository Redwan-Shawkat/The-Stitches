"""Stitches updating itself from its GitHub releases, as on Linux. The check is
one API call; the install uses the same file a new user would download: the
.msi for a copy the .msi put in Program Files, Stitches.exe for the portable
one. See ai-knowledgebase.md ("Windows: Self-update")."""

import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
from .updates import download, get_json

# GitHub redirects the API after a repository rename, so this keeps working
# until it's updated to the new name.
REPO = "Redwan-Shawkat/The-Uninstaller"
_ASSETS = {"msi": "Stitches-*-x64.msi", "exe": "Stitches.exe"}


def parse_version(tag: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", tag)[:3])


def is_newer(tag: str, current: str = __version__) -> bool:
    return parse_version(tag) > parse_version(current)


def install_kind(frozen: bool, exe: Path, program_files: Path) -> str:
    """How this copy got here, which decides how to update it: "msi" (the
    .msi's copy in Program Files), "exe" (the portable Stitches.exe, wherever
    it was put), or "checkout" (Python from a source checkout: git pull)."""
    if not frozen:
        return "checkout"
    return "msi" if exe.is_relative_to(program_files) else "exe"


def pick_asset(release: dict, kind: str):
    pattern = _ASSETS.get(kind)
    return next((a for a in release.get("assets", []) if pattern and fnmatch.fnmatch(a["name"], pattern)), None)


# ---- IO below ----


def _kind() -> str:
    return install_kind(getattr(sys, "frozen", False), Path(sys.executable),
                        Path(os.environ.get("ProgramFiles", r"C:\Program Files")))


def latest() -> tuple[dict | None, str]:
    """(the newest release if it's newer than this copy, why GitHub couldn't be
    asked at all). A startup check still says nothing when it fails — that's
    never worth a dialog — but a check the user asked for can now say why
    instead of claiming this is the newest. Every failure is caught, not just
    OSError and ValueError: http.client's exceptions are neither, and one of
    those killed the worker thread, so the check answered nothing at all."""
    try:
        release = get_json(f"https://api.github.com/repos/{REPO}/releases/latest")
    except Exception as exc:  # noqa: BLE001 - an unreachable GitHub is not a crash
        return None, str(exc) or type(exc).__name__
    return (release if is_newer(release.get("tag_name", "")) else None), ""


def install(release: dict) -> tuple[bool, str]:
    """Downloads and checks the new copy, then puts it in place. The .msi
    is handed to Windows Installer, which asks for permission itself and
    replaces this copy once it has closed; the portable .exe is swapped in
    here. Either way, restart() is what comes next."""
    kind = _kind()
    if kind == "checkout":
        return False, "This copy runs from a source checkout; update it with git pull."
    asset = pick_asset(release, kind)
    if not asset:
        return False, f"Release {release.get('tag_name')} has no {_ASSETS[kind]} to install."
    tmp = Path(tempfile.mkdtemp(prefix="stitches-update-"))
    file = tmp / asset["name"]
    try:
        download(asset["browser_download_url"], file, asset.get("size"), asset.get("digest") or "")
        if kind == "msi":
            os.startfile(file)  # what double-clicking it does; it stays in %TEMP% for Windows Installer to read
            return True, ""
        # A running .exe can't be overwritten, but it can be renamed out of the way.
        exe = Path(sys.executable)
        old = exe.with_suffix(".old")
        old.unlink(missing_ok=True)
        exe.rename(old)
        try:
            shutil.move(file, exe)
        except OSError:
            old.rename(exe)
            raise
        shutil.rmtree(tmp, ignore_errors=True)
        return True, ""
    except OSError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        return False, str(exc)


def restart():
    """Start the new copy; the caller closes this one. After an .msi there's
    nothing to start yet: Windows Installer is still at work, and the Start
    menu entry opens the new version once it's done."""
    if _kind() == "exe":
        # Without this, a onefile build's child reuses this copy's unpacked
        # files, which go when this copy exits (PyInstaller 6.9+; _MEIPASS2 before).
        env = {k: v for k, v in os.environ.items() if k != "_MEIPASS2"}
        subprocess.Popen([sys.executable, *sys.argv[1:]], env={**env, "PYINSTALLER_RESET_ENVIRONMENT": "1"})


def tidy():
    """The copy an update replaced, renamed aside because it was running."""
    if _kind() == "exe":
        try:
            Path(sys.executable).with_suffix(".old").unlink(missing_ok=True)
        except OSError:
            pass  # the old copy is still closing; next start gets it
