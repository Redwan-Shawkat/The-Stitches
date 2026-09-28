"""Flatpak backend. `--app` (not `--app --runtime`) already excludes runtimes/
platforms, so every row here is a real user-facing app: always Safe."""

import re
import subprocess

from ..models import App, Risk, Source

_COLUMNS = "name,application,version,size"
_SIZE_RE = re.compile(r"([\d.]+)\s*([A-Za-z]+)")
_UNITS = {"b": 1, "bytes": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}


def parse_size(text: str) -> int:
    match = _SIZE_RE.match(text.strip())
    if not match:
        return 0
    value, unit = match.groups()
    return int(float(value) * _UNITS.get(unit.lower(), 1))


def parse_flatpak_list(output: str) -> list[dict]:
    """Pure parse of `flatpak list --app --columns=<_COLUMNS>` (tab-separated,
    no header)."""
    rows = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        name, app_id, version, size = parts
        rows.append({"name": name, "id": app_id, "version": version, "size": size})
    return rows


def build_apps(rows: list[dict]) -> list[App]:
    return [
        App(
            name=row["name"],
            id=row["id"],
            source=Source.FLATPAK,
            version=row["version"],
            size_bytes=parse_size(row["size"]),
            risk=Risk.SAFE,
            risk_reason="A sandboxed app — removing it doesn't affect other apps.",
        )
        for row in rows
    ]


class FlatpakBackend:
    def scan(self) -> list[App]:
        out = subprocess.run(
            ["flatpak", "list", "--app", "--columns", _COLUMNS],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return build_apps(parse_flatpak_list(out))

    def uninstall(self, app: App) -> tuple[bool, str]:
        result = subprocess.run(
            ["flatpak", "uninstall", "-y", app.id],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            # system-wide install owned by root: retry with pkexec
            result = subprocess.run(
                ["pkexec", "flatpak", "uninstall", "-y", "--system", app.id],
                capture_output=True,
                text=True,
                check=False,
            )
        return result.returncode == 0, (result.stderr or result.stdout).strip()
