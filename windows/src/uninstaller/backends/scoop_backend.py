"""Scoop backend.

Scoop installs nothing into the registry and nothing into Program Files — a
Scoop app is a folder and a shim, completely invisible to Apps & Features.
That's the Windows version of the gap this project exists to close, and it's
the same shape as Wine on the Linux side: read each app's own manifest out of
its install directory, no CLI call needed to list.
"""

import json
import os
from pathlib import Path

from ..elevate import run
from ..models import App, Source
from ..risk import classify_managed_package


def parse_manifest(text: str) -> str:
    """Pure parse: a Scoop manifest's version string, or "" if unreadable."""
    try:
        return str(json.loads(text).get("version", ""))
    except (ValueError, AttributeError):
        return ""


def install_roots() -> list[tuple[Path, str]]:
    """(directory, scope) for the per-user and machine-wide Scoop roots."""
    user = Path(os.environ.get("SCOOP") or Path.home() / "scoop")
    machine = Path(os.environ.get("SCOOP_GLOBAL") or r"C:\ProgramData\scoop")
    return [(user, "user"), (machine, "machine")]


def read_packages(roots: list[tuple[Path, str]]) -> list[dict]:
    packages = []
    for root, scope in roots:
        apps_dir = root / "apps"
        if not apps_dir.is_dir():
            continue
        for folder in sorted(apps_dir.iterdir()):
            manifest = folder / "current" / "manifest.json"
            if not manifest.is_file():
                continue
            packages.append(
                {
                    "name": folder.name,
                    "version": parse_manifest(
                        manifest.read_text(encoding="utf-8", errors="replace")
                    ),
                    "scope": scope,
                    "shim": str(root / "shims" / "scoop.cmd"),
                }
            )
    return packages


def build_apps(packages: list[dict]) -> list[App]:
    apps = []
    for package in packages:
        risk, reason, is_system = classify_managed_package(package["name"], Source.SCOOP)
        apps.append(
            App(
                name=package["name"],
                id=package["name"],
                source=Source.SCOOP,
                version=package["version"],
                is_system=is_system,
                risk=risk,
                risk_reason=reason,
                extra={"scope": package["scope"], "shim": package["shim"]},
            )
        )
    return apps


class ScoopBackend:
    def scan(self) -> list[App]:
        return build_apps(read_packages(install_roots()))

    def uninstall(self, app: App) -> tuple[bool, str]:
        shim = app.extra.get("shim", "")
        scoop = shim if shim and Path(shim).is_file() else "scoop"
        argv = [scoop, "uninstall", app.id]
        machine_wide = app.extra.get("scope") == "machine"
        if machine_wide:
            argv.append("--global")
        code, output = run(argv, elevated=machine_wide)
        return code == 0, output
