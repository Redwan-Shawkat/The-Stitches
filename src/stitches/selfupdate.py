"""Stitches updating itself from its GitHub releases. The check is one API call;
the install uses the same file a new user would download: the .deb for a
system install, the source tarball (and its install.sh) for a per-user one.
See ai-knowledgebase.md ("Self-update")."""

import fnmatch
import os
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

from . import __version__
from .shell import run
from .updates import get_json, download

# GitHub redirects the API after a repository rename, so this keeps working
# until it's updated to the new name.
REPO = "Redwan-Shawkat/The-Uninstaller"
_ASSETS = {"deb": "stitches_*_all.deb", "user": "stitches-*.tar.gz"}


def parse_version(tag: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", tag)[:3])


def is_newer(tag: str, current: str = __version__) -> bool:
    return parse_version(tag) > parse_version(current)


def install_kind(package_dir: Path, home: Path) -> str:
    """How this copy got here, which decides how to update it: "deb"
    (/usr/lib, via apt), "user" (install.sh's ~/.local/lib), or "checkout"
    (running from a git clone, which git pull updates)."""
    if package_dir.is_relative_to("/usr"):
        return "deb"
    if package_dir.is_relative_to(home / ".local/lib"):
        return "user"
    return "checkout"


def pick_asset(release: dict, kind: str):
    pattern = _ASSETS.get(kind)
    return next((a for a in release.get("assets", []) if pattern and fnmatch.fnmatch(a["name"], pattern)), None)


# ---- IO below ----


def latest():
    """The newest release if it's newer than this copy, else None — also when
    offline or rate-limited: a failed check is never worth a dialog."""
    try:
        release = get_json(f"https://api.github.com/repos/{REPO}/releases/latest")
    except (OSError, ValueError):
        return None
    return release if is_newer(release.get("tag_name", "")) else None


def install(release: dict) -> tuple[bool, str]:
    kind = install_kind(Path(__file__).resolve().parent, Path.home())
    if kind == "checkout":
        return False, "This copy runs from a source checkout; update it with git pull."
    asset = pick_asset(release, kind)
    if not asset:
        return False, f"Release {release.get('tag_name')} has no {_ASSETS[kind]} to install."
    tmp = Path(tempfile.mkdtemp(prefix="stitches-update-"))
    try:
        file = tmp / asset["name"]
        download(asset["browser_download_url"], file, asset.get("size"), asset.get("digest") or "")
        if kind == "deb":
            return run(["pkexec", "apt-get", "install", "-y", str(file)])
        with tarfile.open(file) as archive:
            # "data" refuses absolute paths and links out of the folder; older Pythons lack filters.
            archive.extractall(tmp, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        script = next(tmp.glob("*/install.sh"), None)
        return run(["bash", str(script)]) if script else (False, "The release archive has no install.sh.")
    except (OSError, tarfile.TarError) as exc:
        return False, str(exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def restart():
    """Replace this process with the newly installed copy. The launcher's
    PYTHONPATH is still in the environment, so it resolves the same way."""
    os.execv(sys.executable, [sys.executable, "-m", "stitches", *sys.argv[1:]])
