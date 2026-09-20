"""Microsoft Store backend (MSIX/Appx).

Store apps keep no Uninstall registry key, so the registry backend can't see
them at all — the same gap Snap fills on the Linux side. PowerShell's
`Get-AppxPackage` is the only enumerator Windows exposes, asked for CSV
rather than JSON because CSV is one shape whether it returns one package or
three hundred (`ConvertTo-Json` collapses a single result to an object).
"""

import csv
import io

from ..elevate import powershell
from ..models import App, Source
from ..risk import classify_store_package

_PROPERTIES = "Name,PackageFullName,Version,IsFramework,NonRemovable"
_SCAN = (
    f"Get-AppxPackage | Select-Object {_PROPERTIES} | ConvertTo-Csv -NoTypeInformation"
)


def _truthy(value: str) -> bool:
    return str(value).strip().lower() == "true"


def parse_appx_csv(output: str) -> list[dict]:
    """Pure parse of the CSV `Get-AppxPackage | ConvertTo-Csv` emits."""
    rows = []
    for row in csv.DictReader(io.StringIO(output.lstrip())):
        name = (row.get("Name") or "").strip()
        full_name = (row.get("PackageFullName") or "").strip()
        if not name or not full_name:
            continue
        rows.append(
            {
                "name": name,
                "full_name": full_name,
                "version": (row.get("Version") or "").strip(),
                "is_framework": _truthy(row.get("IsFramework", "")),
                "non_removable": _truthy(row.get("NonRemovable", "")),
            }
        )
    return rows


def build_apps(rows: list[dict]) -> list[App]:
    apps = []
    for row in rows:
        risk, reason, is_system = classify_store_package(
            row["name"], row["is_framework"], row["non_removable"]
        )
        apps.append(
            App(
                name=row["name"],
                id=row["full_name"],
                source=Source.STORE,
                version=row["version"],
                is_system=is_system,
                risk=risk,
                risk_reason=reason,
                # ponytail: Get-AppxPackage reports no size. Getting one means
                # walking InstallLocation per package — add it if sorting by
                # size on Store apps turns out to matter.
            )
        )
    return apps


class StoreBackend:
    def scan(self) -> list[App]:
        code, output = powershell(_SCAN)
        if code != 0:
            return []
        return build_apps(parse_appx_csv(output))

    def uninstall(self, app: App) -> tuple[bool, str]:
        code, output = powershell(f"Remove-AppxPackage -Package '{app.id}'")
        if code == 0:
            return True, ""
        # Provisioned/all-users packages refuse a per-user removal; retry with
        # elevation, the same escalate-on-failure path the Linux build uses
        # for a system-wide Flatpak.
        code, output = powershell(
            f"Remove-AppxPackage -Package '{app.id}' -AllUsers", elevated=True
        )
        return code == 0, output
