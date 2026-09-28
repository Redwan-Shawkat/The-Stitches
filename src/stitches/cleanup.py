"""Cache and temp cleanup: what can be reclaimed, where it lives, and removing
it. Every location carries the path or command it acts on so the GUI can
show exactly what goes, and nothing here runs until the GUI has asked
(CLAUDE.md non-negotiable). See ai-knowledgebase.md ("Cleanup")."""

import os
import re
import shlex
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path

from .backends.flatpak_backend import parse_size
from .leftovers import delete_paths, path_size
from .models import Risk
from .shell import output as _out, run
from .updates import parse_flatpak_rows

_DAY = 86400


@dataclass
class Location:
    name: str
    where: str  # the path or command, shown under the name
    risk: Risk
    reason: str
    items: list[tuple[str, int]]  # (what, bytes): one removal-log line each
    command: list[str] = field(default_factory=list)  # run this; empty = delete `items` as paths
    admin: bool = False  # asks for a password

    @property
    def size_bytes(self) -> int:
        return sum(size for _, size in self.items)


def parse_snap_disabled(output: str) -> list[tuple[str, str]]:
    """`snap list --all` rows whose Notes say disabled -> [(name, revision)].
    Snap keeps each snap's previous revisions around for rollback."""
    found = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 6 and "disabled" in parts[-1].split(","):
            found.append((parts[0], parts[2]))
    return found


def parse_flatpak_unused(output: str) -> list[tuple[str, str]]:
    """The table `flatpak uninstall --unused` prints before asking to go
    ahead -> [(id, branch)]. Rows look like ` 1.   org.gnome.Platform   46   r`."""
    return [m.groups() for m in re.finditer(r"^\s*\d+\.\s+(?:\[.\]\s+)?(\S+)\s+(\S+)", output, re.M)]


def is_stale(path: Path, uid: int, cutoff: float) -> bool:
    """A temp entry that's ours, untouched since `cutoff`, and holds no
    socket — a running ssh-agent or tmux keeps one in /tmp for its whole life."""
    try:
        if path.lstat().st_uid != uid:
            return False
        tree = path.rglob("*") if path.is_dir() and not path.is_symlink() else ()
        for entry in (path, *tree):
            st = entry.lstat()
            if stat.S_ISSOCK(st.st_mode) or st.st_mtime > cutoff:
                return False
        return True
    except OSError:
        return False


# ---- IO below ----


def _children(folder: Path, skip=()) -> list[tuple[str, int]]:
    if not folder.is_dir():
        return []
    return [(str(p), path_size(p)) for p in sorted(folder.iterdir()) if p.name not in skip]


def _files_size(pattern_root: Path, pattern: str, older_than: float = float("inf")) -> int:
    total = 0
    for f in pattern_root.glob(pattern):
        try:
            st = f.stat()
        except OSError:
            continue
        if f.is_file() and st.st_mtime < older_than:
            total += st.st_size
    return total


def _one(label: str, size: int) -> list[tuple[str, int]]:
    return [(label, size)] if size else []


def _apt_cache() -> Location:
    archives = Path("/var/cache/apt/archives")
    size = _files_size(archives, "*.deb") + _files_size(archives, "partial/*")
    return Location("APT package cache", str(archives), Risk.SAFE,
                    "Copies of installers apt already used. Installed packages stay installed; apt downloads one "
                    "again if it needs it.",
                    _one(f"{archives}/*.deb", size), ["pkexec", "apt-get", "clean"], admin=True)


def _snap_revisions() -> Location:
    revisions = parse_snap_disabled(_out(["snap", "list", "--all"]))
    script = " && ".join(shlex.join(["snap", "remove", name, f"--revision={rev}"]) for name, rev in revisions)
    items = [(f"snap {name} revision {rev}", _files_size(Path("/var/lib/snapd/snaps"), f"{name}_{rev}.snap"))
             for name, rev in revisions]
    return Location("Old Snap revisions", "snap list --all · disabled", Risk.SAFE,
                    "Older versions Snap keeps for rolling back. Every app stays installed, at the version you use.",
                    items, ["pkexec", "sh", "-c", script], admin=True)


def _journal(now: float) -> Location:
    size = _files_size(Path("/var/log/journal"), "*/*.journal*", older_than=now - 7 * _DAY)
    return Location("Logs older than 7 days", "journalctl --vacuum-time=7d", Risk.SAFE,
                    "System logs from more than a week ago; the last week stays.",
                    _one("journal files older than 7 days", size),
                    ["pkexec", "journalctl", "--vacuum-time=7d"], admin=True)


def _flatpak_unused() -> Location:
    # Asks flatpak itself what's unused. It prints the list, then asks whether
    # to go ahead — and with no terminal to answer it says no by itself (the
    # reason CI scripts need -y). The "n" on stdin is belt and braces.
    unused = parse_flatpak_unused(_out(["flatpak", "uninstall", "--unused"], answer="n\n"))
    sizes = {}
    for ref, size in parse_flatpak_rows(_out(["flatpak", "list", "--runtime", "--columns=ref,size"]), 2):
        parts = ref.split("/")
        sizes[(parts[0], parts[-1])] = parse_size(size)
    return Location("Unused Flatpak runtimes", "flatpak uninstall --unused", Risk.CAUTION,
                    "Shared runtimes no installed app uses. Your apps stay; one installed later may download "
                    "it again.",
                    [(f"{i}//{b}", sizes.get((i, b), 0)) for i, b in unused],
                    ["flatpak", "uninstall", "--unused", "-y", "--noninteractive"])


def _temp(now: float) -> Location:
    uid, cutoff, items = os.getuid(), now - _DAY, []
    for base in (Path("/tmp"), Path("/var/tmp")):
        try:
            entries = sorted(base.iterdir())
        except OSError:
            continue
        items += [(str(p), path_size(p)) for p in entries if is_stale(p, uid, cutoff)]
    return Location("Temp files older than a day", "/tmp · /var/tmp", Risk.CAUTION,
                    "Only yours, untouched for a day and not in use, but a program may still expect one.", items)


def _trash(home: Path) -> Location:
    trash = home / ".local/share/Trash"
    return Location("Trash", "~/.local/share/Trash", Risk.CAUTION,
                    "Files you deleted, kept until now. This is your own data: nothing can be restored after this.",
                    _one(str(trash), path_size(trash) if trash.is_dir() else 0), ["gio", "trash", "--empty"])


def scan() -> list[Location]:
    """Every location with something in it. One whose tool isn't installed
    (no snap, no flatpak) just isn't listed."""
    home, now = Path.home(), time.time()
    cache = home / ".cache"
    makers = (
        _apt_cache,
        _snap_revisions,
        lambda: Location("App caches", "~/.cache", Risk.SAFE,
                         "Files apps rebuild on their own, like web page caches. Not your documents or settings; "
                         "an app may start slower once.",
                         _children(cache, skip={"thumbnails"})),
        lambda: Location("Thumbnails", "~/.cache/thumbnails", Risk.SAFE,
                         "Image previews, redrawn the next time a folder is opened.", _children(cache / "thumbnails")),
        lambda: _journal(now),
        _flatpak_unused,
        lambda: _temp(now),
        lambda: _trash(home),
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
    if location.command:
        ok, text = run(location.command)
        if not ok:
            log(location.where, 0, text.splitlines()[-1])
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
