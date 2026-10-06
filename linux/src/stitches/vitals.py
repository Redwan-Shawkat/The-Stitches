"""Live readings for Home: temperatures, fans, memory, how full each
partition is, and disk health. All read from /sys and /proc, lsblk, and
UDisks2 over D-Bus (the source GNOME Disks uses) — no root, nothing to
install. Diagnose reuses the disk health. See ai-knowledgebase.md ("Home")."""

import json
from dataclasses import dataclass
from pathlib import Path

from .defrag import parse_lsblk
from .shell import output

GOOD, WARNING, CRITICAL = "Good", "Warning", "Critical"
# hwmon chip name prefix -> what a person calls it
_CHIPS = (
    ("coretemp", "CPU"), ("k10temp", "CPU"), ("zenpower", "CPU"), ("cpu_thermal", "CPU"),
    ("amdgpu", "GPU"), ("radeon", "GPU"), ("nouveau", "GPU"), ("nvme", "NVMe SSD"),
    ("drivetemp", "Disk"), ("acpitz", "Motherboard"), ("pch", "Chipset"), ("iwlwifi", "Wi-Fi"),
    ("nct", "Motherboard"), ("it8", "Motherboard"), ("asus", "Motherboard"), ("thinkpad", "Laptop"),
    ("dell", "Laptop"),
)


@dataclass
class Reading:
    name: str
    value: float  # °C for temperatures, RPM for fans
    status: str = GOOD


@dataclass
class Partition:
    name: str  # mountpoint, or "Not mounted"
    device: str
    fstype: str
    used: int  # 0 when not mounted: usage is unknown
    size: int
    status: str = GOOD


def chip_label(chip: str) -> str:
    return next((label for prefix, label in _CHIPS if chip.startswith(prefix)), chip)


def temp_status(celsius: float, high: float | None = None, crit: float | None = None) -> str:
    """Against the chip's own limits when it reports them (coretemp says high
    80°, critical 100°). Critical starts 5° short of the chip's critical point,
    where it throttles or shuts down; with no limits reported, 75° and 90°."""
    danger = crit - 5 if crit else (high or 75) + 15
    high = high or (crit - 20 if crit else 75)
    return CRITICAL if celsius >= danger else WARNING if celsius >= high else GOOD


def usage_status(used: int, size: int) -> str:
    share = used / size if size else 0
    return CRITICAL if share >= 0.95 else WARNING if share >= 0.85 else GOOD


def group_temps(chip: str, readings: list[tuple[str, float, float | None, float | None]]) -> list[Reading]:
    """One chip's (label, °C, high, crit) readings. A CPU with 16 cores
    reports 17 temperatures; past three, show the first (the package) and
    the hottest of the rest."""
    rows = [Reading(f"{chip} · {label}" if label else chip if len(readings) == 1 else f"{chip} {i + 1}",
                    c, temp_status(c, high, crit))
            for i, (label, c, high, crit) in enumerate(readings)]
    if len(rows) <= 3:
        return rows
    hottest = max(rows[1:], key=lambda r: r.value)
    return [rows[0], Reading(f"{chip} · hottest of {len(rows) - 1} more", hottest.value, hottest.status)]


def parse_meminfo(text: str) -> dict[str, int]:
    """/proc/meminfo -> {field: bytes}."""
    fields = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            fields[key] = int(parts[0]) * 1024
    return fields


def parse_drives(text: str) -> list[dict]:
    """UDisks2 GetManagedObjects, as `busctl --json=short` prints it -> one
    dict per drive: model, smart (has data), failing, warnings, bad_sectors,
    attrs_failing, temp_c, hours. ATA drives and NVMe report differently."""
    def val(props, key, default=None):
        return props.get(key, {}).get("data", default)

    try:
        objects = json.loads(text)["data"][0]
    except (ValueError, KeyError, IndexError):
        return []
    drives = []
    for path, ifaces in sorted(objects.items()):
        drive = ifaces.get("org.freedesktop.UDisks2.Drive")
        if not drive:
            continue
        ata = ifaces.get("org.freedesktop.UDisks2.Drive.Ata", {})
        nvme = ifaces.get("org.freedesktop.UDisks2.NVMe.Controller", {})
        info = {"model": val(drive, "Model") or val(drive, "Vendor") or path.rsplit("/", 1)[-1],
                "smart": False, "failing": False, "warnings": [], "bad_sectors": 0, "attrs_failing": 0,
                "temp_c": None, "hours": None}
        if val(ata, "SmartSupported") and val(ata, "SmartUpdated", 0):
            kelvin = val(ata, "SmartTemperature", 0)
            info.update(smart=True, failing=val(ata, "SmartFailing", False),
                        bad_sectors=val(ata, "SmartNumBadSectors", 0),
                        attrs_failing=val(ata, "SmartNumAttributesFailing", 0),
                        temp_c=round(kelvin - 273.15) if kelvin > 0 else None,
                        hours=val(ata, "SmartPowerOnSeconds", 0) // 3600)
        elif val(nvme, "SmartUpdated", 0):
            kelvin = val(nvme, "SmartTemperature", 0)
            warnings = val(nvme, "SmartCriticalWarning", [])
            info.update(smart=True, failing=bool(warnings), warnings=warnings,
                        temp_c=round(kelvin - 273.15) if kelvin > 0 else None,
                        hours=val(nvme, "SmartPowerOnHours", 0))
        drives.append(info)
    return drives


def drive_health(d: dict) -> tuple[str, str]:
    """(status, plain words) for one drive from parse_drives."""
    if not d["smart"]:
        return "Info", "No health data (USB drives and some adapters don't pass it through)"
    if d["failing"]:
        extra = f" ({', '.join(d['warnings'])})" if d["warnings"] else ""
        return CRITICAL, f"The drive reports it is failing{extra}: back up now"
    if d["bad_sectors"] or d["attrs_failing"]:
        return WARNING, (f"{d['bad_sectors']} bad sectors, {d['attrs_failing']} health values past their limit: "
                         "keep backups current and watch it")
    if d["temp_c"] is not None and d["temp_c"] >= 60:
        return WARNING, f"Healthy, but running hot at {d['temp_c']} °C"
    return GOOD, "Healthy"


# ---- IO below ----


def _read(path) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def _milli(path) -> float | None:
    """hwmon temperatures are millidegrees; None when absent or unreadable."""
    text = _read(path)
    return int(text) / 1000 if text.lstrip("-").isdigit() else None


def read_sensors(root: str = "/sys/class/hwmon") -> tuple[list[Reading], list[Reading]]:
    temps, fans = [], []
    for chip_dir in sorted(Path(root).glob("hwmon*")):
        chip = chip_label(_read(chip_dir / "name"))
        readings = []
        for sensor in sorted(chip_dir.glob("temp*_input"), key=lambda p: (len(p.name), p.name)):
            base = str(sensor)[: -len("_input")]
            celsius = _milli(sensor)
            if celsius is not None and 0 < celsius < 150:  # 0 and 127 °C are what dead sensors say
                readings.append((_read(base + "_label"), celsius, _milli(base + "_max"), _milli(base + "_crit")))
        temps += group_temps(chip, readings)
        for sensor in sorted(chip_dir.glob("fan*_input")):
            rpm = _read(sensor)
            if rpm.isdigit():
                label = _read(str(sensor)[: -len("_input")] + "_label") or sensor.name.split("_")[0]
                fans.append(Reading(f"{chip} · {label}", int(rpm)))
    return temps, fans


# Every drive's SMART data, as GNOME Disks reads it: UDisks2, no root needed.
UDISKS_CALL = ["busctl", "--system", "--json=short", "call", "org.freedesktop.UDisks2", "/org/freedesktop/UDisks2",
               "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"]


def read_drives() -> list[dict]:
    try:
        return parse_drives(output(UDISKS_CALL))
    except OSError:
        return []


def read_memory() -> dict[str, int]:
    return parse_meminfo(_read("/proc/meminfo"))


def read_partitions() -> list[Partition]:
    try:
        rows = parse_lsblk(output(["lsblk", "-J", "-b", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINT,FSUSED,FSSIZE"]))
    except (OSError, ValueError):
        return []
    parts = []
    for r in rows:
        size, used = int(r.get("fssize") or r.get("size") or 0), int(r.get("fsused") or 0)
        parts.append(Partition(r.get("mountpoint") or "Not mounted", r["name"], r["fstype"], used, size,
                               usage_status(used, size) if r.get("mountpoint") else GOOD))
    return sorted(parts, key=lambda p: p.name == "Not mounted")


def uptime() -> str:
    seconds = int(float((_read("/proc/uptime") or "0").split()[0]))
    days, rest = divmod(seconds, 86400)
    return (f"{days} d " if days else "") + f"{rest // 3600} h {rest % 3600 // 60} min"
