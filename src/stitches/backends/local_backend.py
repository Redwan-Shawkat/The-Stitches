"""Per-user copies of this app that install.sh put under ~/.local. No package
manager knows about them, so without this Stitches could list every app on
the machine except itself. Copies installed under its earlier names
(SoftHUB, The Uninstaller) are recognised too."""

import re
from pathlib import Path

from ..leftovers import delete_paths, path_size
from ..models import App, Source
from ..risk import classify_local

# (install name, desktop/app id, what to call it)
INSTALLS = (
    ("stitches", "io.github.stitches", "Stitches"),
    ("softhub", "io.github.softhub", "SoftHUB (old Stitches)"),
    ("linux-the-uninstaller", "io.github.linux-the-uninstaller", "The Uninstaller (old Stitches)"),
)


def install_paths(home: Path, name: str, app_id: str) -> list[Path]:
    """Exactly what install.sh places, which is what uninstall.sh removes."""
    return [
        home / ".local/lib" / name,
        home / ".local/bin" / name,
        home / ".local/share/applications" / f"{app_id}.desktop",
        home / ".local/share/icons/hicolor/scalable/apps" / f"{app_id}.svg",
    ]


def _version(lib: Path) -> str:
    for init in lib.glob("*/__init__.py"):
        m = re.search(r'__version__ = "([^"]+)"', init.read_text(errors="replace"))
        if m:
            return m.group(1)
    return ""


class LocalBackend:
    def scan(self) -> list[App]:
        home, running = Path.home(), Path(__file__).resolve().parents[1]
        apps = []
        for name, app_id, label in INSTALLS:
            paths = install_paths(home, name, app_id)
            if not paths[0].is_dir():
                continue
            risk, reason, is_system = classify_local(running.is_relative_to(paths[0]))
            apps.append(App(label, name, Source.LOCAL, _version(paths[0]), path_size(paths[0]), is_system,
                            risk, reason, extra={"paths": [str(p) for p in paths]}))
        return apps

    def uninstall(self, app: App) -> tuple[bool, str]:
        _freed, errors = delete_paths([p for p in map(Path, app.extra["paths"]) if p.exists() or p.is_symlink()])
        return not errors, "; ".join(f"{p}: {e}" for p, e in errors)
