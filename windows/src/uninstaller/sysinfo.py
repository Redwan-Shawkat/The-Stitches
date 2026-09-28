"""What this PC is and how it's doing, for Home: the spec, the BIOS/UEFI
settings that matter explained in words, memory and drives. Read from the
registry and a few Win32 calls through ctypes: no admin, no PowerShell, no
WMI, so it's quick enough to read again every few seconds.

Same shape as the Linux build's sysinfo.py and vitals.py, in one module
because on Windows each reading is a line or two."""

import ctypes
import os
import re
import shutil
import sys
from datetime import date

try:
    import winreg
except ImportError:  # not Windows: the pure functions below still work
    winreg = None

GOOD, WARNING, CRITICAL, INFO = "Good", "Warning", "Critical", "Info"
# What the BIOS says when the maker left the field blank; common on self-built desktops.
_PLACEHOLDERS = {"", "system manufacturer", "system product name", "to be filled by o.e.m.",
                 "default string", "not applicable", "not specified"}


def windows_name(product: str, display_version: str, build: str, ubr: int) -> str:
    """Windows 11 still says "Windows 10" in ProductName; the build number is
    what tells them apart (22000 and up is 11)."""
    if build.isdigit() and int(build) >= 22000:
        product = product.replace("Windows 10", "Windows 11")
    name = " ".join(p for p in (product or "Windows", display_version) if p)
    return f"{name} · build {build}.{ubr}" if build else name


def cpu_name(raw: str, threads: int) -> str:
    """"Intel(R) Core(TM) i7-8550U CPU @ 1.80GHz" -> "Intel Core i7-8550U · 8 threads"."""
    name = re.sub(r"\((R|TM|tm)\)| CPU| Processor| @ .*|\s+\d+-Core", "", raw).strip() or "Unknown CPU"
    return f"{' '.join(name.split())} · {threads} threads"


def pick_model(bios: dict) -> str:
    vendor, product = bios.get("SystemManufacturer", ""), bios.get("SystemProductName", "")
    if product.lower() in _PLACEHOLDERS:
        vendor, product = bios.get("BaseBoardManufacturer", ""), bios.get("BaseBoardProduct", "")
    return " ".join(p for p in (vendor, product) if p.lower() not in _PLACEHOLDERS) or "Unknown"


def uptime_text(seconds: float) -> str:
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    parts = [f"{days} day{'s' * (days != 1)}"] if days else []
    return " ".join(parts + [f"{hours} h", f"{rest // 60} min"])


def usage_status(used: int, size: int) -> str:
    share = used / size if size else 0
    return CRITICAL if share >= 0.95 else WARNING if share >= 0.85 else GOOD


def describe_firmware(facts: dict, today: date) -> list[tuple[str, str, str, str]]:
    """BIOS/UEFI facts -> (setting, value, what it means, status) rows. The
    meaning is the point: "Secure Boot: On" tells nobody anything; what it
    lets through does. A fact Windows couldn't give is left out."""
    rows = []
    if facts.get("bios_version"):
        year = re.search(r"(\d{4})", facts.get("bios_date", ""))
        age = today.year - int(year.group(1)) if year else None
        rows.append(("BIOS", f"{facts.get('bios_vendor', '')} {facts['bios_version']}".strip(),
                     f"Released {facts.get('bios_date') or 'on an unknown date'}"
                     + (f", {age} years ago" if age else "")
                     + (". Your PC maker's support page may have a newer one." if age and age >= 5 else "."), INFO))
    uefi = facts.get("uefi")
    if uefi is not None:
        rows.append(("Boot mode", "UEFI" if uefi else "Legacy BIOS",
                     "Modern firmware boot; Secure Boot and Windows 11 depend on it." if uefi else
                     "Old-style boot (CSM). It works, but Secure Boot and Windows 11 need UEFI.",
                     GOOD if uefi else INFO))
    if uefi:
        on = facts.get("secure_boot")
        rows.append(("Secure Boot", "On" if on else "Off",
                     "Only signed boot loaders and drivers can start, which blocks boot-level malware." if on else
                     "Anything can boot, including unsigned drivers. Turn it on in BIOS setup unless "
                     "something you use needs it off.", GOOD if on else INFO))
    tpm = facts.get("tpm")
    if tpm is not None:
        rows.append(("TPM", tpm or "Not found",
                     "Security chip that guards BitLocker keys and Windows Hello; Windows 11 needs 2.0."
                     if tpm == "2.0" else "An older security chip; Windows 11 needs TPM 2.0." if tpm else
                     "No security chip found, or it's switched off in BIOS setup (look for fTPM / PTT).",
                     GOOD if tpm == "2.0" else INFO))
    virt = facts.get("virt")
    if virt is not None:
        rows.append(("Virtualization", "On" if virt else "Off",
                     "WSL 2, Windows Sandbox and virtual machines run at full hardware speed." if virt else
                     "Turned off in BIOS setup, or not supported. Turn on Intel VT-x / AMD SVM there "
                     "for WSL 2, Hyper-V and virtual machines.", GOOD if virt else INFO))
    return rows


# ---- IO below: everything returns something empty off Windows ----


def _reg(path: str, *names: str) -> dict:
    """HKLM values that exist, as {name: value}."""
    if winreg is None:
        return {}
    values = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            for name in names:
                try:
                    values[name] = winreg.QueryValueEx(key, name)[0]
                except OSError:
                    pass
    except OSError:
        pass
    return values


def _bios() -> dict:
    return _reg(r"HARDWARE\DESCRIPTION\System\BIOS", "SystemManufacturer", "SystemProductName",
                "BaseBoardManufacturer", "BaseBoardProduct", "BIOSVendor", "BIOSVersion", "BIOSReleaseDate")


def _gpus() -> str:
    """The display adapters' names, from the display class key (every GPU driver writes one there)."""
    if winreg is None:
        return "—"
    names = []
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    for i in range(8):
        name = _reg(rf"{base}\{i:04}", "DriverDesc").get("DriverDesc")
        if name and name not in names:
            names.append(name)
    return " · ".join(names) or "—"


def read_spec() -> list[tuple[str, str]]:
    nt = _reg(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "ProductName", "DisplayVersion", "ReleaseId",
              "CurrentBuild", "UBR")
    cpu = _reg(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
    installed = ctypes.c_ulonglong()
    if sys.platform == "win32" and ctypes.windll.kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(installed)):
        memory = f"{round(installed.value / 1024 ** 2)} GB"
    else:
        memory = "—"
    return [
        ("Model", pick_model(_bios())),
        ("Windows", windows_name(nt.get("ProductName", ""), nt.get("DisplayVersion") or nt.get("ReleaseId", ""),
                                 str(nt.get("CurrentBuild", "")), nt.get("UBR", 0))),
        ("CPU", cpu_name(cpu.get("ProcessorNameString", ""), os.cpu_count() or 1)),
        ("GPU", _gpus()),
        ("Memory", memory),
    ]


def read_uptime() -> str:
    if sys.platform != "win32":
        return "—"
    ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    return uptime_text(ctypes.windll.kernel32.GetTickCount64() / 1000)


def _tpm_version():
    """"2.0", "1.2", "" when there's none, None when Windows can't say."""

    class _DeviceInfo(ctypes.Structure):  # TBS_DEVICE_INFO
        _fields_ = [("structVersion", ctypes.c_uint32), ("tpmVersion", ctypes.c_uint32),
                    ("tpmInterfaceType", ctypes.c_uint32), ("tpmImpRevision", ctypes.c_uint32)]

    info = _DeviceInfo()
    try:
        result = ctypes.windll.tbs.Tbsi_GetDeviceInfo(ctypes.sizeof(info), ctypes.byref(info))
    except (AttributeError, OSError):
        return None
    if result & 0xFFFFFFFF == 0x8028400F:  # TBS_E_TPM_NOT_FOUND
        return ""
    return {1: "1.2", 2: "2.0"}.get(info.tpmVersion) if result == 0 else None


def read_firmware() -> list[tuple[str, str, str, str]]:
    if sys.platform != "win32":
        return []
    bios = _bios()
    kernel32 = ctypes.windll.kernel32
    firmware = ctypes.c_uint32()
    uefi = firmware.value == 2 if kernel32.GetFirmwareType(ctypes.byref(firmware)) else None  # 1 BIOS, 2 UEFI
    state = _reg(r"SYSTEM\CurrentControlSet\Control\SecureBoot\State", "UEFISecureBootEnabled")
    return describe_firmware({
        "bios_vendor": bios.get("BIOSVendor", ""), "bios_version": bios.get("BIOSVersion", ""),
        "bios_date": bios.get("BIOSReleaseDate", ""), "uefi": uefi,
        "secure_boot": state.get("UEFISecureBootEnabled") == 1, "tpm": _tpm_version(),
        "virt": bool(kernel32.IsProcessorFeaturePresent(21)),  # PF_VIRT_FIRMWARE_ENABLED
    }, date.today())


def read_memory() -> tuple[int, int]:
    """(used, total) bytes of RAM."""
    if sys.platform != "win32":
        return 0, 0

    class _Status(ctypes.Structure):  # MEMORYSTATUSEX
        _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    status = _Status(dwLength=ctypes.sizeof(_Status))
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullTotalPhys - status.ullAvailPhys, status.ullTotalPhys


def read_drives() -> list[tuple[str, str, int, int]]:
    """(letter, "label · filesystem", used, size) for each local drive with a disk in it."""
    if sys.platform != "win32":
        return []
    kernel32 = ctypes.windll.kernel32
    mask, drives = kernel32.GetLogicalDrives(), []
    for i in range(26):
        root = f"{chr(65 + i)}:\\"
        if not mask >> i & 1 or kernel32.GetDriveTypeW(root) not in (2, 3):  # removable, fixed
            continue
        label, fs = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
        if not kernel32.GetVolumeInformationW(root, label, 261, None, None, None, fs, 261):
            continue  # a card reader with no card in it
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue
        drives.append((root[:2], " · ".join(p for p in (label.value, fs.value) if p), usage.used, usage.total))
    return drives
