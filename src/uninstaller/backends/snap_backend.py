"""Snap backend."""

import subprocess

from ..models import App, Risk, Source
from ..risk import classify_runtime_name


def parse_snap_list(output: str) -> list[dict]:
    """Pure parse of `snap list` output (header line + one row per snap)."""
    lines = output.splitlines()[1:]  # drop header
    rows = []
    for line in lines:
        parts = line.split()
        if len(parts) < 5:
            continue
        name, version, _rev, _tracking = parts[0], parts[1], parts[2], parts[3]
        rows.append({"name": name, "version": version})
    return rows


def build_apps(rows: list[dict]) -> list[App]:
    apps = []
    for row in rows:
        runtime = classify_runtime_name(row["name"])
        if runtime:
            risk, reason, is_system = runtime
        else:
            risk, reason, is_system = (
                Risk.SAFE,
                "A standalone snap app — nothing else is known to depend on it.",
                False,
            )
        apps.append(
            App(
                name=row["name"],
                id=row["name"],
                source=Source.SNAP,
                version=row["version"],
                is_system=is_system,
                risk=risk,
                risk_reason=reason,
                # ponytail: `snap list` has no size column; `snap info` would add
                # it at one subprocess call per snap. Upgrade if size sorting matters.
            )
        )
    return apps


class SnapBackend:
    def scan(self) -> list[App]:
        out = subprocess.run(
            ["snap", "list"], capture_output=True, text=True, check=False
        ).stdout
        return build_apps(parse_snap_list(out))

    def uninstall(self, app: App) -> tuple[bool, str]:
        result = subprocess.run(
            ["pkexec", "snap", "remove", app.id],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0, (result.stderr or result.stdout).strip()
