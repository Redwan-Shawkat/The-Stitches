"""Drivers: the hardware a person would recognise, the driver each runs on,
and the driver updates Windows Update offers for them. Windows keeps its own
driver catalogue, so unlike Linux there's one place to ask; vendor tools
(GeForce Experience, Adrenalin) stay theirs. See ai-knowledgebase.md
("Windows: Drivers")."""

import re
from dataclasses import dataclass

from .elevate import powershell
from .updates import parse_wu, wu_install_script, wu_search_script

# Device setup classes shown, by the name Win32_PnPSignedDriver gives them.
_KINDS = {"DISPLAY": "Display", "NET": "Network", "MEDIA": "Audio", "SCSIADAPTER": "Storage", "HDC": "Storage",
          "BLUETOOTH": "Bluetooth", "FIRMWARE": "Firmware"}
_DEVICES = (
    "Get-CimInstance Win32_PnPSignedDriver | Where-Object DeviceName | ForEach-Object {\n"
    "  $d = if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } else { '' }\n"
    "  @($_.DeviceName, $_.DeviceClass, $_.DriverVersion, $d, $_.DriverProviderName, $_.DeviceID) -join \"`t\"\n"
    "}\n"
)


@dataclass
class Driver:
    name: str
    kind: str
    version: str
    released: str  # the date its maker gave this version: the update's if there is one
    purpose: str  # what it is, in words
    update_id: str = ""  # Windows Update's id when there's a newer one
    new_version: str = ""
    size_bytes: int = 0


def purpose(kind: str, provider: str) -> str:
    if kind == "Firmware":
        return "Firmware: runs inside the device itself, whatever OS starts on it"
    return f"Windows driver for this {kind.lower()} device" + (f", from {provider}" if provider else "")


def is_hardware(device_id: str) -> bool:
    """A real device, not one Windows made up in software (ROOT\\, SWD\\):
    WAN miniports, virtual audio, the Remote Desktop adapter."""
    return not device_id.upper().startswith(("ROOT\\", "SWD\\", "SW\\"))


def parse_devices(text: str) -> list[Driver]:
    found, seen = [], set()
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 6:
            continue
        name, klass, version, released, provider, device_id = (p.strip() for p in parts)
        kind = _KINDS.get(klass.upper())
        if kind and is_hardware(device_id) and (name, version) not in seen:
            seen.add((name, version))
            found.append(Driver(name, kind, version, released, purpose(kind, provider)))
    return sorted(found, key=lambda d: (list(_KINDS.values()).index(d.kind), d.name.lower()))


def version_from_title(title: str) -> str:
    """Windows Update names a driver "Intel Corporation - Display - 31.0.101.4502"."""
    last = title.rsplit(" - ", 1)[-1]
    return last if re.fullmatch(r"[\d.]+", last) else ""


def merge(devices: list[Driver], updates: list[dict]) -> list[Driver]:
    """Each update onto the device it's for, matched by model name; an update
    for a device not in the list (a class it doesn't show) gets its own row."""
    by_name = {d.name.lower(): d for d in devices}
    extra = []
    for u in updates:
        kind = "Firmware" if u["class"].lower() == "firmware" else _KINDS.get(u["class"].upper(), "Other")
        row = by_name.get(u["model"].lower())
        if row is None:
            row = Driver(u["model"] or u["title"], kind, "", "", purpose(kind, ""))
            extra.append(row)
        row.update_id, row.new_version, row.size_bytes = u["id"], version_from_title(u["title"]) or "newer", u["size"]
        row.released = u["released"] or row.released
    return devices + extra


# ---- IO below ----


def scan() -> list[Driver]:
    devices = parse_devices(powershell(_DEVICES)[1])
    return merge(devices, parse_wu(powershell(wu_search_script("Driver"))[1]))


def update(drivers: list[Driver]) -> tuple[bool, str]:
    """Every chosen driver in one go, behind one permission prompt."""
    code, text = powershell(wu_install_script([d.update_id for d in drivers]), elevated=True)
    return code == 0, text
