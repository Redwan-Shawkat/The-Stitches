"""App Manager, as on Linux: which catalog apps are installed, at what version,
and installing the rest through winget, one at a time (each installer asks
for permission itself, as winget updates do). What winget knows comes from
one `winget export`; an app it doesn't know is still found by its command on
PATH. Whether an install worked is decided by looking again, not by the exit
code. Pure helpers first, then the subprocess calls."""

import json
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .catalog import CATALOG, App
from .elevate import run

_VERSION_RE = re.compile(r"\d+(?:\.\d+)+[\w.+~-]*")


@dataclass
class Status:
    installed: bool
    version: str = ""  # empty while installed means it couldn't be read, not that it's missing
    via: str = ""  # winget, or how a command on PATH got there (Scoop, Chocolatey…; just PATH if it can't tell)
    path: str = ""


NOT_INSTALLED = Status(False)


def parse_export(text: str) -> dict[str, str]:
    """`winget export --include-versions`'s JSON -> {lowercased id: version}.
    winget ids aren't case-sensitive."""
    try:
        data = json.loads(text or "{}")
    except ValueError:
        return {}
    return {p["PackageIdentifier"].lower(): p.get("Version", "")
            for source in data.get("Sources", []) for p in source.get("Packages", []) if "PackageIdentifier" in p}


def via_path(path: str) -> str:
    low = path.lower()
    for marker, via in (("\\scoop\\", "Scoop"), ("chocolatey", "Chocolatey"), ("\\.cargo\\", "rustup")):
        if marker in low:
            return via
    return "PATH"


def is_store_stub(path: str) -> bool:
    """WindowsApps\\python.exe is Windows' "get it from the Store" stand-in, not Python."""
    return "\\windowsapps\\" in path.lower()


def parse_version(text: str) -> str:
    m = _VERSION_RE.search(text)
    return m.group(0) if m else ""


def readable(line: str):
    """A winget output line as the Terminal should show it: what's after the
    last \r (it redraws its progress bar in place), or None for a spinner frame."""
    line = line.rsplit("\r", 1)[-1].strip()
    return line if line and not set(line) <= set("-\\|/ ") else None


def detect(app: App, installed: dict[str, str], find_command) -> Status:
    version = installed.get(app.package.lower())
    if version is not None:
        return Status(True, version, "winget")
    path = find_command(app.command) if app.command else None
    return Status(True, "", via_path(path), path) if path and not is_store_stub(path) else NOT_INSTALLED


def install_command(app: App) -> list[str]:
    """The id comes from the catalog, never from what someone typed."""
    return ["winget", "install", "--id", app.package, "--exact", "--source", "winget", "--silent",
            "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"]


# ---- IO below ----


def installed_packages() -> dict[str, str]:
    folder = Path(tempfile.mkdtemp(prefix="stitches-"))
    file = folder / "installed.json"
    try:
        # It exits non-zero when some apps have no winget source; the file is still written.
        run(["winget", "export", "-o", str(file), "--include-versions", "--accept-source-agreements",
             "--disable-interactivity"], encoding="utf-8")
        return parse_export(file.read_text(encoding="utf-8-sig"))
    except OSError:
        return {}  # no winget (Windows 10 without App Installer)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _command_version(app: App, status: Status) -> Status:
    if status.installed and not status.version and status.path:
        argv = [status.path, *(app.version[1:] if app.version else ["--version"])]
        lines = []
        run(argv, on_line=lines.append)  # streamed: stdout and stderr both (java -version prints to stderr)
        status.version = parse_version("\n".join(lines))
    return status


def check(apps=CATALOG) -> list[Status]:
    installed = installed_packages()
    statuses = [detect(a, installed, shutil.which) for a in apps]
    with ThreadPoolExecutor() as pool:
        return list(pool.map(_command_version, apps, statuses))


def install(app: App, on_line=None) -> tuple[int, str]:
    return run(install_command(app), on_line=on_line, encoding="utf-8")
