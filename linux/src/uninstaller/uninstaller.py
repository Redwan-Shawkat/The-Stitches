"""Orchestrates one uninstall: run the right backend, then look for leftovers.
Confirmation before either step is the GUI's job (CLAUDE.md: non-negotiable),
not this module's."""

from pathlib import Path

from .leftovers import delete_paths, find_leftovers
from .models import App
from .scanner import backend_for


def uninstall(app: App) -> tuple[bool, str, list[Path]]:
    """Removes the app, then returns leftover paths found afterward (not yet
    deleted — the caller shows them and asks before deleting)."""
    backend = backend_for(app)
    ok, message = backend.uninstall(app)
    leftovers = find_leftovers(app.name, [app.id]) if ok else []
    return ok, message, leftovers


def clean_leftovers(paths: list[Path]) -> tuple[int, list[tuple[Path, str]]]:
    """Returns (bytes_freed, [(path, error) for failures])."""
    return delete_paths(paths)
