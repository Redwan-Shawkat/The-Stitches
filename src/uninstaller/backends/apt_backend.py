"""APT/dpkg backend: covers `apt install`, `dpkg -i some.deb`, and anything
else dpkg knows about. See ai-knowledgebase.md for why `apt-mark showmanual`
is the source list rather than every installed package."""

import subprocess

from ..models import App, Source
from ..risk import classify_apt

_FIELD_SEP = "\t"
_FMT = _FIELD_SEP.join(
    ("${Package}", "${Version}", "${Installed-Size}", "${Priority}", "${Essential}")
) + "\n"


def parse_dpkg_query(output: str) -> dict[str, dict]:
    """Pure parse of `dpkg-query -W -f=<_FMT>` output -> {package: fields}."""
    fields = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split(_FIELD_SEP)
        if len(parts) != 5:
            continue
        name, version, size_kb, priority, essential = parts
        try:
            size_bytes = int(size_kb or 0) * 1024
        except ValueError:
            size_bytes = 0
        fields[name] = {
            "version": version,
            "size_bytes": size_bytes,
            "priority": priority,
            "essential": essential,
        }
    return fields


def parse_showmanual(output: str) -> set[str]:
    return {line.strip() for line in output.splitlines() if line.strip()}


def build_apps(manual: set[str], dpkg_fields: dict[str, dict]) -> list[App]:
    apps = []
    for name in manual:
        info = dpkg_fields.get(name, {})
        risk, reason, is_system = classify_apt(
            info.get("priority", ""), info.get("essential", "")
        )
        apps.append(
            App(
                name=name,
                id=name,
                source=Source.APT,
                version=info.get("version", ""),
                size_bytes=info.get("size_bytes", 0),
                is_system=is_system,
                risk=risk,
                risk_reason=reason,
            )
        )
    return apps


class AptBackend:
    def scan(self) -> list[App]:
        manual_out = subprocess.run(
            ["apt-mark", "showmanual"], capture_output=True, text=True, check=False
        ).stdout
        dpkg_out = subprocess.run(
            ["dpkg-query", "-W", "-f", _FMT], capture_output=True, text=True, check=False
        ).stdout
        return build_apps(parse_showmanual(manual_out), parse_dpkg_query(dpkg_out))

    def uninstall(self, app: App) -> tuple[bool, str]:
        result = subprocess.run(
            ["pkexec", "apt-get", "purge", "-y", app.id],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return True, ""
        # dpkg runs the package's own postrm/prerm script as part of purge —
        # a broken one (bad maintainer script, missing debconf sourcing, etc.)
        # fails the whole command even though dpkg already deleted the
        # package's files first. Check dpkg's own bookkeeping instead of
        # trusting the exit code, so a package that's actually gone still
        # gets its leftovers found (find_leftovers only runs when this
        # returns ok=True) instead of looking like nothing happened.
        status = subprocess.run(
            ["dpkg-query", "-W", "-f", "${Status}", app.id], capture_output=True, text=True, check=False
        ).stdout.strip()
        message = (result.stderr or result.stdout).strip()
        if status.endswith("config-files") or status.endswith("not-installed") or not status:
            return True, f"Removed, but dpkg reported a cleanup error: {message}"
        return False, message
