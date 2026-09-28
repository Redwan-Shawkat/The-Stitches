"""Diagnose: Linux's answers to sfc /scannow, DISM, chkdsk, a disk-health
readout and the Windows Memory Diagnostic. Every check reads without root;
a fix that needs root goes through pkexec, and one that needs a restart
says so and asks first. Each check hands log(line) what it runs and what
that prints, as it prints it. See ai-knowledgebase.md ("Diagnose")."""

import json
import re
import shlex
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import sysinfo, vitals
from .models import format_size
from .shell import output, run, tail
from .updates import APT_KEEP_CONFIG

OK, WARNING, PROBLEM, INFO = "OK", "Warning", "Problem", "Info"
_VERIFY_RE = re.compile(r"^(\S{9}|missing)\s+(c?)\s*(/.+?)(?: \(([^)]*)\))?$")
_SAVE_WORK = "Save your work first."


@dataclass
class Fix:
    label: str
    command: list[str]
    caution: str = ""  # asked before running; empty means the button is the confirmation
    restart: bool = False  # offer to restart once it's done


@dataclass
class Result:
    status: str
    summary: str
    details: list[str] = field(default_factory=list)
    fix: Fix | None = None


@dataclass
class Check:
    title: str
    like: str  # the Windows tool it stands in for
    run: object  # (log) -> Result


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' * (n != 1)}"


def parse_verify(text: str, diverted: set[str]) -> tuple[list[str], list[str], int]:
    """`dpkg --verify` -> (changed, missing, unchecked). Config files are
    skipped: they're meant to be edited. "?" or "Permission denied" means it
    couldn't be read without root. A diverted file's moved original is
    deliberate, not missing."""
    changed, missing, unchecked = [], [], 0
    for line in text.splitlines():
        m = _VERIFY_RE.match(line)
        if not m:
            continue
        flags, conffile, path, error = m.groups()
        if conffile or path in diverted:
            continue
        if flags == "missing":
            if error:
                unchecked += 1
            else:
                missing.append(path)
        elif flags[2] == "5":
            changed.append(path)
        elif flags[2] == "?":
            unchecked += 1
    return changed, missing, unchecked


def parse_diversions(text: str) -> set[str]:
    return set(re.findall(r"diversion of \S+ to (\S+)", text))


def parse_owners(text: str) -> dict[str, str]:
    """`dpkg -S <paths>` ("pkg1, pkg2: /path") -> {path: first package}."""
    owners = {}
    for line in text.splitlines():
        packages, sep, path = line.partition(": ")
        if sep and not line.startswith("diversion"):
            owners[path.strip()] = packages.split(",")[0].strip()
    return owners


def parse_failed_units(text: str) -> list[str]:
    return [line.split()[0] for line in text.splitlines() if line.strip()]


def parse_journal(text: str) -> Counter:
    """`journalctl -o json` lines -> errors counted per program."""
    counts = Counter()
    for line in text.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        counts[entry.get("SYSLOG_IDENTIFIER") or entry.get("_COMM") or "unknown"] += 1
    return counts


def memory_test(size: int) -> int | None:
    """Writes five patterns over `size` bytes and reads each back. None if
    every byte held, else the offset of the first 1 MiB block that didn't.
    It can only test memory the OS hands it — a fault in RAM that the kernel
    or other apps are using stays invisible — hence the full test at restart."""
    chunk = 1 << 20
    size -= size % chunk
    buf = bytearray(size)
    counting = bytes(range(256)) * (chunk // 256)
    for pattern in (b"\x00" * chunk, b"\xff" * chunk, b"\x55" * chunk, b"\xaa" * chunk, counting):
        for off in range(0, size, chunk):
            buf[off:off + chunk] = pattern
        for off in range(0, size, chunk):
            if buf[off:off + chunk] != pattern:  # a copy, but memcmp-fast; memoryview compares per byte
                return off
    return None


# ---- the checks (IO) ----


def _read(log, argv: list[str], show: bool = True) -> str:
    """output(argv), with the command and each line it prints going to log.
    show=False for JSON, which is no use to read."""
    log(f"$ {shlex.join(argv)}")
    return output(argv, on_line=log if show else None)


def disk_health(log) -> Result:
    log("Reading each drive's SMART data through UDisks2…")
    drives = vitals.read_drives()
    if not drives:
        return Result(INFO, "Couldn't reach UDisks2, so drive health can't be read.")
    rows = [(d, *vitals.drive_health(d)) for d in drives]
    details = [f"{d['model']}: {words}" + (f" · {d['temp_c']} °C" if d["temp_c"] is not None else "")
               + (f" · {d['hours']:,} hours powered on" if d["hours"] else "") for d, _, words in rows]
    if any(status == vitals.CRITICAL for _, status, _ in rows):
        return Result(PROBLEM, "A drive reports it is failing. Back up what matters now.", details)
    if any(status == vitals.WARNING for _, status, _ in rows):
        return Result(WARNING, "A drive needs attention.", details)
    return Result(OK, f"{plural(len(drives), 'drive')} checked by their own SMART self-monitoring.", details)


def _check_at_restart(devices: list[str]) -> Fix:
    script = " && ".join(shlex.join(["tune2fs", "-E", "force_fsck", f"/dev/{d}"]) for d in devices)
    return Fix("Check at next restart", ["pkexec", "sh", "-c", script],
               f"The next restart checks and repairs {', '.join(devices)} before the desktop starts. On a big "
               "disk that takes several minutes; don't switch the PC off while it runs. " + _SAVE_WORK,
               restart=True)


def file_systems(log) -> Result:
    errors = {}
    for fs in sorted(Path("/sys/fs/ext4").glob("*/errors_count")):
        errors[fs.parent.name] = int((fs.read_text().strip() or "0"))
        log(f"{fs}: {errors[fs.parent.name]}")
    if not errors:
        return Result(INFO, "No ext4 file systems mounted, so there's nothing to check live.")
    bad = {dev: n for dev, n in errors.items() if n}
    if bad:
        return Result(PROBLEM, f"The kernel recorded errors on {', '.join(bad)}.",
                      [f"{dev}: {plural(n, 'error')} since the last check" for dev, n in bad.items()],
                      _check_at_restart(list(bad)))
    return Result(OK, f"No errors recorded on {plural(len(errors), 'ext4 file system')}. A full check "
                      "can still be run at the next restart.", [f"{dev}: clean" for dev in errors],
                  _check_at_restart(list(errors)))


def free_space(log) -> Result:
    log("Measuring every mounted partition…")
    parts = [p for p in vitals.read_partitions() if p.name != "Not mounted" and p.size]
    full = [p for p in parts if p.status != vitals.GOOD]
    details = [f"{p.name}: {format_size(p.size - p.used)} free of {format_size(p.size)}" for p in parts]
    if not full:
        return Result(OK, "Every mounted partition has room.", details)
    return Result(PROBLEM if any(p.status == vitals.CRITICAL for p in full) else WARNING,
                  f"Almost full: {', '.join(p.name for p in full)}. The Cleanup tool can free space.", details)


def services(log) -> Result:
    system = parse_failed_units(_read(log, ["systemctl", "--failed", "--no-legend", "--plain"]))
    session = parse_failed_units(_read(log, ["systemctl", "--user", "--failed", "--no-legend", "--plain"]))
    if not system and not session:
        return Result(OK, "No services have failed.")
    return Result(PROBLEM, f"{plural(len(system) + len(session), 'service')} failed to start or crashed.",
                  system + [f"{u} (your session)" for u in session],
                  Fix(f"Restart {plural(len(system), 'service')}", ["pkexec", "systemctl", "restart", *system])
                  if system else None)


def logged_errors(log) -> Result:
    counts = parse_journal(_read(log, ["journalctl", "-b", "-p", "err", "-q", "--no-pager", "-o", "json"], show=False))
    total = sum(counts.values())
    if not total:
        return Result(OK, "No errors logged since startup.")
    top = ", ".join(name for name, _ in counts.most_common(3))
    return Result(INFO, f"{plural(total, 'error')} logged since startup, mostly from {top}. Many are harmless; "
                        "they matter when they line up with a problem you're seeing.",
                  [f"{name}: {n}" for name, n in counts.most_common(10)])


def package_database(log) -> Result:
    audit = _read(log, ["dpkg", "--audit"]).strip()
    argv = ["apt-get", "check", "-o", "Debug::NoLocking=1"]
    log(f"$ {shlex.join(argv)}")
    ok, text = run(argv, on_line=log)
    if not audit and ok:
        return Result(OK, "No half-installed packages and no broken dependencies.")
    return Result(PROBLEM, "Some packages are half-installed or have broken dependencies.",
                  audit.splitlines() + tail(text).splitlines(),
                  Fix("Repair packages", ["pkexec", "sh", "-c", "dpkg --configure -a && apt-get -f install -y"]))


def memory_quick(log) -> Result:
    size = min(1 << 30, vitals.read_memory().get("MemAvailable", 0) // 4)
    if size < 64 << 20:
        return Result(INFO, "Too little free memory to test right now. Close some apps and scan again.")
    log(f"Writing 5 patterns over {format_size(size)} of free memory and reading each back…")
    bad = memory_test(size)
    if bad is not None:
        return Result(PROBLEM, f"Memory {format_size(bad)} into the test didn't hold what was written: "
                               "a RAM stick may be failing. Run the full test at restart to confirm.")
    return Result(OK, f"Wrote and read back {format_size(size)} of free memory with 5 patterns: no errors.",
                  ["This covers only memory that wasn't in use. The test at restart checks every byte."])


def memory_at_restart(log) -> Result:
    efi = Path("/sys/firmware/efi").is_dir()
    log("Looking for memtest86+ in /boot…")
    if not Path("/boot/memtest86+x64.efi" if efi else "/boot/memtest86+x64.bin").exists():
        return Result(INFO, "memtest86+ isn't installed, so there's no memory test to restart into.",
                      fix=Fix("Install memtest86+", ["pkexec", "apt-get", "install", "-y", "memtest86+"]))
    caution = ("The next start (only that one) boots memtest86+ instead of Linux. It tests every byte of RAM and "
               "takes from half an hour to a few hours; press Esc to stop it and the PC starts normally. " + _SAVE_WORK)
    if efi and sysinfo.secure_boot():
        caution += ("\n\nSecure Boot is on and memtest86+ isn't signed, so the firmware may refuse to start it — "
                    "the PC then just starts Linux as usual. Turn Secure Boot off in BIOS setup to run the test.")
    return Result(INFO, "Tests all of the RAM before Linux starts, like the Windows Memory Diagnostic.",
                  fix=Fix("Restart into memory test", ["pkexec", "grub-reboot", "memtest86+"], caution, restart=True))


def system_files(log) -> Result:
    diverted = parse_diversions(_read(log, ["dpkg-divert", "--list"]))
    changed, missing, unchecked = parse_verify(_read(log, ["dpkg", "--verify"]), diverted)
    bad = changed + missing
    note = [f"{plural(unchecked, 'file')} can only be checked with admin rights (kernel images in /boot and "
            "the like)."] if unchecked else []
    if not bad:
        return Result(OK, "Every installed file matches the package it came from.", note)
    packages = sorted(set(parse_owners(_read(log, ["dpkg", "-S", *bad])).values()))
    return Result(PROBLEM, f"{plural(len(bad), 'system file')} changed or missing, from "
                           f"{plural(len(packages), 'package')}.",
                  [f"changed: {p}" for p in changed] + [f"missing: {p}" for p in missing] + note,
                  Fix(f"Reinstall {plural(len(packages), 'package')}",
                      ["pkexec", "apt-get", "install", "--reinstall", "-y", *APT_KEEP_CONFIG, *packages])
                  if packages else None)


# Fast first; the file-by-file package check takes a minute or two.
CHECKS = [
    Check("Disk health", "like CrystalDiskInfo", disk_health),
    Check("File systems", "like chkdsk", file_systems),
    Check("Free space", "like Storage Sense", free_space),
    Check("Services", "like services.msc", services),
    Check("Errors since startup", "like Event Viewer", logged_errors),
    Check("Package database", "like DISM /CheckHealth", package_database),
    Check("Memory, quick", "like the Memory Diagnostic, without restarting", memory_quick),
    Check("Memory, full", "like the Memory Diagnostic", memory_at_restart),
    Check("System files", "like sfc /scannow · takes a minute or two", system_files),
]


def run_check(check: Check, log=lambda _line: None) -> Result:
    """The check, framed in the log by its name and what it found."""
    log(f"▶ {check.title} · {check.like}")
    try:
        result = check.run(log)
    except OSError as exc:  # the tool it needs isn't installed
        result = Result(INFO, f"Couldn't run this check: {exc.strerror or exc}.")
    log(f"{result.status}: {result.summary}")
    return result
