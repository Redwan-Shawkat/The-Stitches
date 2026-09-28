"""Leftover scan: after a package-manager uninstall, look for per-user files
it doesn't own (package managers don't track what an app wrote to
~/.config at runtime). Heuristic name match; never deletes without the
caller showing the list first — see ai-knowledgebase.md."""

import shutil
from pathlib import Path

_LOCATIONS = ("~/.config", "~/.cache", "~/.local/share", "~/.var/app")
_MIN_TERM_LEN = 3  # ponytail: guards against short names matching everything


def find_leftovers(
    app_name: str, extra_terms: list[str] | None = None, home: Path | None = None
) -> list[Path]:
    terms = {t.lower() for t in ({app_name} | set(extra_terms or [])) if len(t) >= _MIN_TERM_LEN}
    home = home or Path.home()
    found = []
    for location in _LOCATIONS:
        base = Path(str(home) + location[1:]) if location.startswith("~") else Path(location)
        if not base.is_dir():
            continue
        for entry in base.iterdir():
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
