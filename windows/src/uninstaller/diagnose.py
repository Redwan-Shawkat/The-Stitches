"""Diagnose: Windows' own health tools behind one Scan — drive health,
file-system state, free space, failed services, logged errors, a restart
Windows is waiting for, a memory test — each with a verdict in words. Every
check reads without admin rights. sfc and DISM can't even look without them,
so those two are fixes you start, not checks that run. Each check hands
log(line) what it runs and what that prints. See ai-knowledgebase.md
("Windows: Diagnose")."""

from collections import Counter
from dataclasses import dataclass, field

from . import sysinfo
from .elevate import powershell
from .models import format_size

try:
    import winreg
except ImportError:  # not Windows: the pure functions below still work
    winreg = None

OK, WARNING, PROBLEM, INFO = "OK", "Warning", "Problem", "Info"
_NEVER_STARTED = "1077"  # a trigger-start service nothing has needed yet: not a failure


@dataclass
class Fix:
    label: str
    script: str  # PowerShell, run with administrator rights
    caution: str = ""  # asked before running; empty means the button is the confirmation


@dataclass
class Result:
    status: str
    summary: str
    details: list[str] = field(default_factory=list)
    fix: Fix | None = None


@dataclass
class Check:
    title: str
    like: str  # the Windows tool it's the same as
    run: object  # (log) -> Result


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' * (n != 1)}"


def _rows(text: str, columns: int) -> list[list[str]]:
    """Tab-separated lines with exactly `columns` fields."""
    return [[p.strip() for p in parts] for parts in (line.split("\t") for line in text.splitlines())
            if len(parts) == columns]


def judge_disks(rows: list[list[str]]) -> Result:
    """Get-PhysicalDisk rows (name, media, health, operational status) ->
    a verdict. Health is the drive's own SMART-based opinion, as Windows reads it."""
    if not rows:
        return Result(INFO, "Windows didn't report any drives' health.")
    details = [f"{name}{f' ({media})' if media not in ('', 'Unspecified') else ''}: {health}"
               + (f", {state}" if state not in ("", "OK") else "") for name, media, health, state in rows]
    if any(r[2] == "Unhealthy" for r in rows):
        return Result(PROBLEM, "A drive reports it is failing. Back up what matters now.", details)
    if any(r[2] == "Warning" for r in rows):
        return Result(WARNING, "A drive needs attention.", details)
    return Result(OK, f"{plural(len(rows), 'drive')} report themselves healthy.", details)


def judge_volumes(rows: list[list[str]]) -> Result:
    """Get-Volume rows (letter, file system, health, operational status) -> a
    verdict, with chkdsk's online scan as the fix: it runs with Windows up,
    no restart."""
    if not rows:
        return Result(INFO, "Windows didn't report any drives' file systems.")
    bad = [r for r in rows if r[2] not in ("Healthy", "")]
    letters = [r[0] for r in rows if r[1] in ("NTFS", "ReFS")]
    fix = Fix(f"Scan {', '.join(f'{letter}:' for letter in letters)}",
              "; ".join(f"chkdsk {letter}: /scan" for letter in letters),
              "chkdsk scans with Windows running and fixes what it can on the spot. On a big drive that takes a "
              "few minutes.") if letters else None
    details = [f"{letter}: {fs or 'no file system'} · {health}" + (f", {state}" if state not in ("", "OK") else "")
               for letter, fs, health, state in rows]
    if bad:
        return Result(PROBLEM, f"Windows found file-system errors on {', '.join(r[0] + ':' for r in bad)}.",
                      details, fix)
    return Result(OK, f"No errors recorded on {plural(len(rows), 'drive')}. A scan can still be run.", details, fix)


def failed_services(rows: list[list[str]]) -> list[list[str]]:
    """Win32_Service rows (name, display name, exit code) of services set to
    start automatically that stopped with an error."""
    return [r for r in rows if r[2] not in ("0", _NEVER_STARTED)]


def count_events(text: str) -> Counter:
    return Counter(line.strip() for line in text.splitlines() if line.strip())


def memory_test(size: int) -> int | None:
    """Writes five patterns over `size` bytes and reads each back. None if
    every byte held, else the offset of the first 1 MiB block that didn't.
    It can only test memory Windows hands it — a fault in RAM that Windows
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


def _read(log, what: str, script: str) -> str:
    """powershell(script)'s output, with `what` it asks going to the log.
    The script's tab-separated lines are for parsing, not reading."""
    log(f"$ {what}")
    return powershell(script)[1]


def disk_health(log) -> Result:
    return judge_disks(_rows(_read(log, "Get-PhysicalDisk", (
        "Get-PhysicalDisk | ForEach-Object { @($_.FriendlyName, $_.MediaType, $_.HealthStatus,"
        " ($_.OperationalStatus -join ',')) -join \"`t\" }")), 4))


def file_systems(log) -> Result:
    return judge_volumes(_rows(_read(log, "Get-Volume", (
        "Get-Volume | Where-Object { \"$($_.DriveLetter)\" -match '^[A-Za-z]$' } | Sort-Object DriveLetter |"
        " ForEach-Object { @($_.DriveLetter, $_.FileSystem, $_.HealthStatus, ($_.OperationalStatus -join ','))"
        " -join \"`t\" }")), 4))


def free_space(log) -> Result:
    log("Measuring every drive…")
    drives = sysinfo.read_drives()
    full = [d for d in drives if sysinfo.usage_status(d[2], d[3]) != sysinfo.GOOD]
    details = [f"{letter} {format_size(size - used)} free of {format_size(size)}" for letter, _, used, size in drives]
    if not full:
        return Result(OK, "Every drive has room.", details)
    critical = any(sysinfo.usage_status(d[2], d[3]) == sysinfo.CRITICAL for d in full)
    return Result(PROBLEM if critical else WARNING,
                  f"Almost full: {', '.join(d[0] for d in full)}. The Cleanup tool can free space.", details)


def services(log) -> Result:
    failed = failed_services(_rows(_read(log, "Get-CimInstance Win32_Service", (
        "Get-CimInstance Win32_Service -Filter \"StartMode='Auto' AND State='Stopped' AND ExitCode<>0\" |"
        " ForEach-Object { @($_.Name, $_.DisplayName, $_.ExitCode) -join \"`t\" }")), 3))
    if not failed:
        return Result(OK, "No services have failed.")
    names = ", ".join(f"'{name}'" for name, _, _ in failed)
    return Result(PROBLEM, f"{plural(len(failed), 'service')} set to start with Windows stopped with an error.",
                  [f"{display} ({name}): error {code}" for name, display, code in failed],
                  Fix(f"Start {plural(len(failed), 'service')}", f"Start-Service -Name {names} -Verbose 4>&1"))


def logged_errors(log) -> Result:
    counts = count_events(_read(log, "Get-WinEvent System, Application · errors since startup", (
        "$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime\n"
        "Get-WinEvent -FilterHashtable @{LogName = 'System', 'Application'; Level = 1, 2; StartTime = $boot}"
        " -ErrorAction SilentlyContinue | ForEach-Object { $_.ProviderName }")))
    total = sum(counts.values())
    if not total:
        return Result(OK, "No errors logged since startup.")
    top = ", ".join(name for name, _ in counts.most_common(3))
    return Result(INFO, f"{plural(total, 'error')} logged since startup, mostly from {top}. Many are harmless; "
                        "they matter when they line up with a problem you're seeing.",
                  [f"{name}: {n}" for name, n in counts.most_common(10)])


def _key_exists(path: str) -> bool:
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path))
        return True
    except OSError:
        return False


def pending_restart(log) -> Result:
    keys = {r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending": "an update",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired": "Windows Update"}
    if winreg is None:
        return Result(INFO, "Only Windows can say.")
    for key in keys:
        log(f"HKLM\\{key}")
    waiting = [who for key, who in keys.items() if _key_exists(key)]
    if waiting:
        return Result(WARNING, f"Windows is waiting for a restart to finish installing {' and '.join(waiting)}. "
                               "Until then, some updates and repairs aren't in effect.")
    return Result(OK, "Nothing is waiting for a restart.")


def memory_quick(log) -> Result:
    used, total = sysinfo.read_memory()
    size = min(1 << 30, (total - used) // 4)
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
    return Result(INFO, "Tests all of the RAM before Windows starts.",
                  fix=Fix("Open Memory Diagnostic", "Start-Process mdsched.exe",
                          "Windows Memory Diagnostic opens and asks whether to restart now or at the next start. "
                          "The test takes from several minutes to an hour; the result shows after you sign in "
                          "again. Save your work first."))


def component_store(log) -> Result:
    return Result(INFO, "DISM checks the store Windows repairs its own files from, and can only look with "
                        "administrator rights.",
                  fix=Fix("Check and repair", "DISM /Online /Cleanup-Image /RestoreHealth",
                          "DISM compares the store against Windows Update and downloads what's damaged. It takes "
                          "5 to 20 minutes."))


def system_files(log) -> Result:
    return Result(INFO, "sfc checks every protected Windows file, and can only look with administrator rights. "
                        "Run it after DISM: it repairs from the store DISM fixes.",
                  fix=Fix("Check and repair", "sfc /scannow",
                          "sfc checks every protected Windows file and puts back any that changed. It takes 5 to "
                          "15 minutes."))


# Fast first; the two that need administrator rights last.
CHECKS = [
    Check("Disk health", "the drives' own SMART health", disk_health),
    Check("File systems", "chkdsk", file_systems),
    Check("Free space", "Storage Sense", free_space),
    Check("Services", "services.msc", services),
    Check("Errors since startup", "Event Viewer", logged_errors),
    Check("Waiting for a restart", "Windows Update", pending_restart),
    Check("Memory, quick", "Memory Diagnostic, without restarting", memory_quick),
    Check("Memory, full", "Windows Memory Diagnostic", memory_at_restart),
    Check("Component store", "DISM /RestoreHealth", component_store),
    Check("System files", "sfc /scannow", system_files),
]


def run_check(check: Check, log=lambda _line: None) -> Result:
    """The check, framed in the log by its name and what it found."""
    log(f"▶ {check.title} · {check.like}")
    try:
        result = check.run(log)
    except OSError as exc:
        result = Result(INFO, f"Couldn't run this check: {exc.strerror or exc}.")
    log(f"{result.status}: {result.summary}")
    for line in result.details:
        log(f"  {line}")
    return result


def run_fix(fix: Fix, log) -> tuple[bool, str]:
    log(f"$ {fix.script}")
    code, text = powershell(fix.script, elevated=True, on_line=log)
    return code == 0, text
