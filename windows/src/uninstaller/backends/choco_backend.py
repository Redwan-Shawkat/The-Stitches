"""Chocolatey backend.

Read straight from `$ChocolateyInstall\\lib\\<pkg>\\<pkg>.nuspec` rather than
shelling out to `choco list`: the folder is the install database, reading it
is instant, and it doesn't break the way the CLI did when Chocolatey 2.0
changed what a bare `choco list` means. Same reasoning as the Linux build
parsing Wine's registry files instead of running `wine uninstaller`.
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path

from ..elevate import run
from ..models import App, Source
from ..risk import classify_managed_package


def parse_nuspec(text: str) -> dict:
    """Pure parse of a .nuspec's id/version/title. Namespaces vary by
    Chocolatey version, so tags are matched on local name."""
    fields = {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return fields
    for element in root.iter():
        tag = element.tag.rpartition("}")[2]
        if tag in ("id", "version", "title") and element.text:
            fields.setdefault(tag, element.text.strip())
    return fields


def install_root() -> Path:
    return Path(os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey"))


def read_packages(root: Path) -> list[dict]:
    lib = root / "lib"
    if not lib.is_dir():
        return []
    packages = []
    for folder in sorted(lib.iterdir()):
        nuspec = folder / f"{folder.name}.nuspec"
        if not nuspec.is_file():
            continue
        fields = parse_nuspec(nuspec.read_text(encoding="utf-8", errors="replace"))
        packages.append(
            {
                "id": fields.get("id", folder.name),
                "name": fields.get("title") or fields.get("id", folder.name),
                "version": fields.get("version", ""),
            }
        )
    return packages


def build_apps(packages: list[dict]) -> list[App]:
    apps = []
    for package in packages:
        risk, reason, is_system = classify_managed_package(package["id"], Source.CHOCOLATEY)
        apps.append(
            App(
                name=package["name"],
                id=package["id"],
                source=Source.CHOCOLATEY,
                version=package["version"],
                is_system=is_system,
                risk=risk,
                risk_reason=reason,
            )
        )
    return apps


class ChocoBackend:
    def scan(self) -> list[App]:
        return build_apps(read_packages(install_root()))

    def uninstall(self, app: App) -> tuple[bool, str]:
        # Chocolatey installs to ProgramData machine-wide, so removal is an
        # administrator operation — elevated, per CLAUDE.md.
        code, output = run(
            ["choco", "uninstall", app.id, "-y", "--no-progress"], elevated=True
        )
        return code == 0, output
