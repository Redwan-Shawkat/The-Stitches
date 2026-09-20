"""Leftover scan: after an uninstaller has run, look for the per-user files it
didn't own (a Windows uninstaller removes what its installer wrote, not what
the program itself created under AppData at runtime). Heuristic name match;
never deletes without the caller showing the list first — see
ai-knowledgebase.md."""

import os
import shutil
from pathlib import Path

# Relative to the user profile, plus ProgramData. Documents and the Registry
# are deliberately not scanned — see ai-knowledgebase.md.
_USER_SUBDIRS = (
    "AppData/Roaming",
    "AppData/Local",
    "AppData/LocalLow",
)
_MIN_TERM_LEN = 3  # ponytail: guards against short names matching everything


def scan_roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    roots = [home / sub for sub in _USER_SUBDIRS]
    program_data = os.environ.get("ProgramData")
    if program_data:
        roots.append(Path(program_data))
    return roots


def find_leftovers(
    app_name: str, extra_terms: list[str] | None = None, home: Path | None = None
) -> list[Path]:
    terms = {t.lower() for t in ({app_name} | set(extra_terms or [])) if len(t) >= _MIN_TERM_LEN}
    found = []
    for base in scan_roots(home):
        if not base.is_dir():
            continue
        try:
            entries = list(base.iterdir())
        except OSError:
            continue  # ProgramData holds directories a normal user can't list
        for entry in entries:
            name = entry.name.lower()
            if any(term in name for term in terms):
                found.append(entry)
    return found


def path_size(path: Path) -> int:
    """Total bytes a leftover occupies, walked before deletion (a deleted
    tree reports 0, so callers must measure before removing it)."""
    try:
        if path.is_symlink() or path.is_file():
            return path.stat().st_size
        total = 0
        for entry in path.rglob("*"):
            if entry.is_file() and not entry.is_symlink():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass  # gone or unreadable mid-walk — skip, don't fail the count
        return total
    except OSError:
        return 0


def delete_paths(paths: list[Path]) -> tuple[int, list[tuple[Path, str]]]:
    """Deletes each path. Returns (bytes_freed, [(path, error) for failures])
    — bytes_freed only counts paths that were actually deleted."""
    freed = 0
    errors = []
    for path in paths:
        size = path_size(path)
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            freed += size
        except OSError as exc:
            errors.append((path, str(exc)))
    return freed, errors
