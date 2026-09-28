"""What this machine is, for Home: the spec, and the BIOS/UEFI settings that
matter explained in words. Read from /proc, /sys and os-release; no root
needed. lspci and lsblk are the only processes started, for GPU and disk
names."""

import json
import math
import os
import re
from datetime import date
from pathlib import Path

from .drivers import parse_lspci
from .shell import output

# What DMI says when the maker left the field blank — common on self-built desktops.
_PLACEHOLDERS = {"", "system manufacturer", "system product name", "to be filled by o.e.m.",
                 "default string", "not applicable", "not specified"}


def parse_os_release(text: str) -> str:
    m = re.search(r'^PRETTY_NAME="?([^"\n]*)"?', text, re.M)
    return m.group(1) if m else "Linux"


def parse_cpuinfo(text: str, threads: int) -> str:
    """"Intel(R) Core(TM) i3-6100 CPU @ 3.70GHz" -> "Intel Core i3-6100 · 2C / 4T"."""
    model = re.search(r"^model name\s*:\s*(.+)$", text, re.M)
    cores = re.search(r"^cpu cores\s*:\s*(\d+)", text, re.M)
    sockets = len(set(re.findall(r"^physical id\s*:\s*(\d+)", text, re.M))) or 1
    name = model.group(1) if model else "Unknown CPU"
    name = re.sub(r"\((R|TM|tm)\)| CPU| Processor| @ .*| with .*|\s+\d+-Core", "", name).strip()
    count = f"{int(cores.group(1)) * sockets}C / {threads}T" if cores else f"{threads} threads"
    return f"{name} · {count}"


def parse_meminfo(text: str) -> str:
    """MemTotal is the installed RAM minus what firmware reserves; round up to
    the number on the box."""
    m = re.search(r"^MemTotal:\s*(\d+) kB", text, re.M)
    return f"{math.ceil(int(m.group(1)) / 1024 ** 2)} GB" if m else "—"


def pick_board(dmi: dict) -> str:
    vendor, product = dmi.get("sys_vendor", ""), dmi.get("product_name", "")
    if product.lower() in _PLACEHOLDERS:
        vendor, product = dmi.get("board_vendor", ""), dmi.get("board_name", "")
    name = " ".join(p for p in (vendor, product) if p.lower() not in _PLACEHOLDERS) or "Unknown"
    return f"{name} · BIOS {dmi['bios_version']}" if dmi.get("bios_version") else name


def disk_label(size_bytes: int) -> str:
    """Drive makers count in powers of 1000, so the label on the box does too."""
    return f"{size_bytes / 1e12:.1f} TB" if size_bytes >= 1e12 else f"{size_bytes / 1e9:.0f} GB"


def describe_firmware(facts: dict, today: date) -> list[tuple[str, str, str, str]]:
    """BIOS/UEFI facts -> (setting, value, what it means, status) rows, with
    status Good, Warning or Info. The meaning is the point: "Secure Boot: On"
    tells nobody anything; what it lets through does."""
    rows = []
    year = re.search(r"(\d{4})", facts.get("bios_date", ""))
    if facts.get("bios_version"):
        age = today.year - int(year.group(1)) if year else None
        rows.append(("BIOS", f"{facts.get('bios_vendor', '')} {facts['bios_version']}".strip(),
                     f"Released {facts['bios_date']}" + (f", {age} years ago" if age else "")
                     + (". The Drivers tool shows it if your board maker offers a newer one." if age and age >= 5
                        else ""), "Info"))
    uefi = facts.get("uefi")
    rows.append(("Boot mode", "UEFI" if uefi else "Legacy BIOS",
                 "Modern firmware boot; Secure Boot and firmware updates depend on it." if uefi else
                 "Old-style boot (CSM). It works, but Secure Boot and most firmware updates need UEFI.",
                 "Good" if uefi else "Info"))
    if uefi:
        on = facts.get("secure_boot")
        rows.append(("Secure Boot", "On" if on else "Off",
                     "Only signed boot loaders and kernels can start, which blocks boot-level malware." if on else
                     "Anything can boot, including unsigned drivers. Some NVIDIA and VirtualBox setups need this.",
                     "Good" if on else "Info"))
    tpm = facts.get("tpm")
    rows.append(("TPM", f"{tpm}.0" if tpm else "Not found",
                 "Security chip that guards disk-encryption keys and checks the boot chain." if tpm else
                 "No security chip found, or it's switched off in BIOS setup (look for fTPM / PTT).",
                 "Good" if tpm else "Info"))
    if facts.get("virt_flag"):
        on = facts.get("kvm")
        rows.append(("Virtualization", "On" if on else "Available",
                     "Virtual machines run at full hardware speed." if on else
                     "The CPU supports it, but KVM isn't loaded, so virtual machines would run slowly.",
                     "Good" if on else "Info"))
    else:
        rows.append(("Virtualization", "Off",
                     "Turned off in BIOS setup, or not supported. Turn on Intel VT-x / AMD SVM there "
                     "to run virtual machines at full speed.", "Info"))
    return rows


# ---- IO below ----


def _read(path: str) -> str:
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return ""


def _disks() -> str:
    # lsblk, not /sys/block/*/device/model: that one cuts ATA models at 16 characters.
    disks = json.loads(output(["lsblk", "-J", "-d", "-b", "-o", "MODEL,SIZE,TYPE"]) or "{}").get("blockdevices", [])
    return " · ".join(f"{d['model']} {disk_label(int(d['size']))}"
                      for d in disks if d.get("type") == "disk" and d.get("model")) or "—"


def secure_boot() -> bool:
    efivar = Path("/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c")
    try:
        return efivar.read_bytes()[-1:] == b"\x01"  # 4 attribute bytes, then the value
    except OSError:
        return False


def read_firmware() -> list[tuple[str, str, str, str]]:
    cpu_flags = re.search(r"^flags\s*:(.*)$", _read("/proc/cpuinfo"), re.M)
    facts = {
        "bios_vendor": _read("/sys/class/dmi/id/bios_vendor"),
        "bios_version": _read("/sys/class/dmi/id/bios_version"),
        "bios_date": _read("/sys/class/dmi/id/bios_date"),
        "uefi": Path("/sys/firmware/efi").is_dir(),
        "secure_boot": secure_boot(),
        "tpm": _read("/sys/class/tpm/tpm0/tpm_version_major") or ("2" if Path("/sys/class/tpm/tpm0").exists() else ""),
        "virt_flag": bool(cpu_flags and {"vmx", "svm"} & set(cpu_flags.group(1).split())),
        "kvm": Path("/dev/kvm").exists(),
    }
    return describe_firmware(facts, date.today())


def read_spec() -> list[tuple[str, str]]:
    dmi = {k: _read(f"/sys/class/dmi/id/{k}")
           for k in ("sys_vendor", "product_name", "board_vendor", "board_name", "bios_version")}
    try:
        gpus = [d["name"] for d in parse_lspci(output(["lspci", "-vmmnnkD"])) if d["code"].startswith("03")]
    except OSError:
        gpus = []
    try:
        disks = _disks()
    except (OSError, ValueError):
        disks = "—"
    return [
        ("OS", parse_os_release(_read("/etc/os-release"))),
        ("Kernel", os.uname().release),
        ("CPU", parse_cpuinfo(_read("/proc/cpuinfo"), os.cpu_count() or 1)),
        ("GPU", " · ".join(gpus) or "—"),
        ("Memory", parse_meminfo(_read("/proc/meminfo"))),
        ("Board", pick_board(dmi)),
        ("Disk", disks),
    ]
