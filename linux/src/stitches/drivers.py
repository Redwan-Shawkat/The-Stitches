"""Hardware detection and driver/firmware updates. Most Linux drivers ship
inside the kernel and update with it; what updates on its own comes from
three places: ubuntu-drivers (proprietary GPU/Wi-Fi drivers), fwupd/LVFS
(device firmware) and the linux-firmware package. Each also says when the
version it offers was released by its maker. See ai-knowledgebase.md
("Drivers")."""

import gzip
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .shell import output as _out, run
from .updates import APT_KEEP_CONFIG, parse_apt_upgradable

UBUNTU_DRIVERS, FWUPD, LINUX_FIRMWARE, KERNEL = "ubuntu-drivers", "fwupd · LVFS", "linux-firmware", "kernel"
# PCI class prefixes worth listing; bridges, SMBus and friends aren't hardware anyone updates.
_KINDS = {"01": "Storage", "02": "Network", "03": "Display", "04": "Audio", "0d": "Wireless"}
_KERNEL_DRIVER = {"Storage": "Disk controller", "Network": "Network", "Display": "Graphics", "Audio": "Sound",
                  "Wireless": "Wireless"}
_ANY_OS = "Firmware: it applies to every OS on this PC, not just Linux."
# fwupd plugin prefix -> what that firmware is; first match wins.
_FIRMWARE = (
    ("uefi_capsule", "Your motherboard's BIOS/UEFI."),
    ("uefi_", "A Secure Boot key list kept in your BIOS; it decides which boot loaders may start."),
    ("ata", "The drive's own firmware."), ("nvme", "The drive's own firmware."), ("scsi", "The drive's own firmware."),
    ("cpu", "Processor microcode."), ("tpm", "The TPM security chip's firmware."),
    ("intel_me", "The Intel Management Engine in your chipset."), ("intel_amt", "Intel AMT remote management."),
    ("amd_gpu", "The graphics card's own firmware."), ("intel_gsc", "The graphics card's own firmware."),
    ("thunderbolt", "The Thunderbolt controller's firmware."), ("intel_usb4", "The USB4 controller's firmware."),
)
_LINUX_FIRMWARE = {"": "Wi-Fi, Bluetooth and graphics", "amd-graphics": "AMD graphics",
                   "nvidia-graphics": "NVIDIA graphics", "intel-graphics": "Intel graphics",
                   "mediatek": "MediaTek Wi-Fi and Bluetooth", "realtek": "Realtek network"}


@dataclass
class Driver:
    device: str
    kind: str  # "Display · amdgpu", "Firmware"
    current: str
    new: str = ""  # empty = nothing to update
    source: str = KERNEL
    id: str = ""  # apt package to install, or fwupd device id
    note: str = ""  # "reboot needed"
    purpose: str = ""  # what it is, and whether it's a Linux driver at all
    released: str = ""  # "2026-08-28": when the newest version came out; empty = not published


def firmware_purpose(plugin: str) -> str:
    what = next((text for prefix, text in _FIRMWARE if plugin.startswith(prefix)), "Firmware inside this device.")
    return f"{what} {_ANY_OS}"


def linux_firmware_purpose(package: str) -> str:
    suffix = package.removeprefix("linux-firmware").strip("-")
    chips = _LINUX_FIRMWARE.get(suffix, suffix.replace("-", " "))
    return f"Files Linux loads into your {chips} chips. Linux only."


def short_name(name: str, vendor: bool = False) -> str:
    """lspci/ubuntu-drivers names -> the part people recognise. The numeric id
    goes; a vendor's bracketed short form wins ("… Inc. [AMD/ATI]" ->
    "AMD/ATI"), else its first word ("Intel Corporation" -> "Intel")."""
    name = re.sub(r"\s*\[[0-9a-f]{4}\]$", "", name.strip())
    if not vendor:
        return name
    m = re.search(r"\[([^\]]+)\]$", name)
    return m.group(1) if m else name.split(" ")[0]


def gpu_name(name: str) -> str:
    """A GPU's marketing name is the bracketed part: "Oland PRO [Radeon R7 240]"
    -> "Radeon R7 240". Only for GPUs: elsewhere brackets say things like
    "[AHCI Mode]"."""
    name = short_name(name)
    m = re.search(r"\[([^\]]+)\]$", name)
    return m.group(1) if m else name


def parse_lspci(output: str) -> list[dict]:
    """`lspci -vmmnnkD` -> [{"slot", "code", "name", "driver"}]."""
    devices = []
    for block in output.strip().split("\n\n"):
        fields = {}
        for line in block.splitlines():
            key, _, value = line.partition(":\t")
            fields.setdefault(key, value)
        code = re.search(r"\[([0-9a-f]{4})\]$", fields.get("Class", ""))
        if code:
            device = fields.get("Device", "")
            devices.append({
                "slot": fields.get("Slot", ""), "code": code.group(1), "driver": fields.get("Driver", ""),
                "name": short_name(fields.get("Vendor", ""), vendor=True) + " "
                + (gpu_name(device) if code.group(1).startswith("03") else short_name(device)),
            })
    return devices


def parse_ubuntu_drivers(output: str) -> list[dict]:
    """`ubuntu-drivers devices` -> [{"slot", "name", "packages", "recommended"}]."""
    devices = []
    for line in output.splitlines():
        if line.startswith("== ") and line.endswith(" =="):
            devices.append({"slot": line[3:-3].rsplit("/", 1)[-1], "vendor": "", "model": "",
                            "packages": [], "recommended": ""})
        elif devices and ":" in line:
            key, value = (s.strip() for s in line.split(":", 1))
            if key in ("vendor", "model"):
                devices[-1][key] = value
            elif key == "driver":
                package, _, flags = value.partition(" - ")
                devices[-1]["packages"].append(package.strip())
                if "recommended" in flags.split():
                    devices[-1]["recommended"] = package.strip()
    for d in devices:
        # ubuntu-drivers only lists devices with a proprietary driver: GPUs, mostly.
        d["name"] = short_name(d.pop("vendor"), vendor=True) + " " + gpu_name(d.pop("model"))
    return devices


def parse_fwupd(text: str) -> list[dict]:
    """`fwupdmgr get-devices --json` or `get-updates --json` -> the devices
    fwupd can flash, with the newest release offered (get-updates only) and
    the day each release LVFS knows of came out."""
    try:
        devices = json.loads(text).get("Devices", [])
    except ValueError:
        return []
    return [
        {"id": d["DeviceId"], "name": d.get("Name", ""), "version": d.get("Version", ""), "plugin": d.get("Plugin", ""),
         "flags": d.get("Flags", []), "update": (d.get("Releases") or [{}])[0].get("Version", ""),
         "released": {r.get("Version", ""): datetime.fromtimestamp(r["Created"], timezone.utc).date().isoformat()
                      for r in d.get("Releases", []) if r.get("Created")}}
        for d in devices if "updatable" in d.get("Flags", [])
    ]


def changelog_date(text: str) -> str:
    """A Debian changelog -> the day its newest entry was released, "2026-08-28"."""
    m = re.search(r"^ -- .*>  (.+)$", text, re.M)
    try:
        return parsedate_to_datetime(m.group(1).strip()).date().isoformat() if m else ""
    except (TypeError, ValueError):
        return ""


def dmi_date(text: str) -> str:
    """The BIOS date as the board reports it, "05/11/2016" -> "2016-05-11"."""
    m = re.fullmatch(r"(\d\d)/(\d\d)/(\d{4})", text.strip())
    return f"{m[3]}-{m[1]}-{m[2]}" if m else ""


def plan_jobs(selected: list[Driver]) -> list[list[Driver]]:
    """Every apt package in one batch (one password prompt); each firmware
    flash on its own, since each is its own device and its own risk."""
    apt = [d for d in selected if d.source in (UBUNTU_DRIVERS, LINUX_FIRMWARE)]
    return ([apt] if apt else []) + [[d] for d in selected if d.source == FWUPD]


def command_for(job: list[Driver]) -> list[str]:
    if job[0].source == FWUPD:
        return ["pkexec", "fwupdmgr", "update", job[0].id, "--assume-yes", "--no-reboot-check"]
    return ["pkexec", "apt-get", "install", "-y", *APT_KEEP_CONFIG, *(d.id for d in job)]


# ---- IO below ----


def _safe(read, default):
    try:
        return read()
    except OSError:
        return default  # that tool isn't installed here


def _released(package: str, pending: bool = False) -> str:
    """When `package`'s newest version came out. The changelog on disk is the
    installed version's, so for a waiting update apt fetches the new one."""
    if pending:
        return changelog_date(_safe(lambda: _out(["timeout", "10", "apt-get", "changelog", package]), ""))
    try:
        with gzip.open(f"/usr/share/doc/{package}/changelog.Debian.gz", "rt", errors="replace") as f:
            return changelog_date(f.read())
    except OSError:
        return ""


def _installed(packages: list[str]) -> set[str]:
    out = _safe(lambda: _out(["dpkg-query", "-W", "-f", "${Package}\t${db:Status-Status}\n", *packages]), "")
    return {line.split("\t")[0] for line in out.splitlines() if line.endswith("\tinstalled")}


def find_drivers() -> list[Driver]:
    pci = _safe(lambda: parse_lspci(_out(["lspci", "-vmmnnkD"])), [])
    kinds = {d["slot"]: _KINDS.get(d["code"][:2], "Device") for d in pci}
    found, covered = [], set()

    for dev in _safe(lambda: parse_ubuntu_drivers(_out(["ubuntu-drivers", "devices"])), []):
        installed = _installed(dev["packages"])
        current = next((p for p in dev["packages"] if p in installed), "open-source driver")
        rec = dev["recommended"]
        covered.add(dev["slot"])
        new = rec if rec and rec not in installed else ""
        found.append(Driver(dev["name"], kinds.get(dev["slot"], "Device"), current, new, UBUNTU_DRIVERS, rec,
                            purpose="The maker's own Linux driver, from Ubuntu, in place of the open-source one.",
                            released=_released(new, pending=True) if new else
                            _released(current) if current in installed else ""))

    offered = {d["id"]: d for d in _safe(lambda: parse_fwupd(_out(["fwupdmgr", "get-updates", "--json"])), [])}
    for dev in _safe(lambda: parse_fwupd(_out(["fwupdmgr", "get-devices", "--json"])), []):
        update = offered.get(dev["id"], {"update": "", "released": {}})
        new = update["update"]
        released = update["released"].get(new, "") if new else dev["released"].get(dev["version"], "")
        if not released and dev["plugin"] == "uefi_capsule":  # the BIOS itself: the board says when it's from
            released = dmi_date(_safe(Path("/sys/class/dmi/id/bios_date").read_text, ""))
        found.append(Driver(dev["name"], "Firmware", dev["version"], new, FWUPD, dev["id"],
                            "reboot needed" if new and "needs-reboot" in dev["flags"] else "",
                            firmware_purpose(dev["plugin"]), released))

    for u in _safe(lambda: parse_apt_upgradable(_out(["apt", "list", "--upgradable"])), []):
        if u.name.startswith("linux-firmware"):
            found.append(Driver(u.name, "Firmware files", u.current, u.new, LINUX_FIRMWARE, u.name,
                                purpose=linux_firmware_purpose(u.name), released=_released(u.name, pending=True)))

    kernel = ".".join(os.uname().release.split(".")[:2])
    kernel_released = _released(f"linux-image-{os.uname().release}")
    for dev in pci:
        kind = _KINDS.get(dev["code"][:2])
        if kind and dev["slot"] not in covered:
            found.append(Driver(dev["name"], f"{kind} · {dev['driver']}" if dev["driver"] else kind,
                                f"In kernel {kernel}" if dev["driver"] else "No driver in use",
                                purpose=f"{_KERNEL_DRIVER[kind]} driver inside the Linux kernel; updates with it.",
                                released=kernel_released))
    return sorted(found, key=lambda d: not d.new)


def apply(job: list[Driver]) -> tuple[bool, str]:
    return run(command_for(job))
