"""Privilege escalation, and every subprocess call that isn't one.

The Linux build shells out to `pkexec` for anything machine-wide. Windows'
equivalent is the UAC consent prompt, which you don't get by running a
command — you get it by asking the shell to launch one with the `runas`
verb. That's `ShellExecuteExW`, which lives in shell32, so ctypes reaches
it with no new dependency. CLAUDE.md non-negotiable: machine-wide removals
go through this, and the password/consent dialog is the OS's, never ours.
"""

import base64
import ctypes
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Keeps a console window from flashing up behind every scan/uninstall call —
# this is a --windowed build, so there's no console to reuse.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SEE_MASK_NO_CONSOLE = 0x00008000
_SW_HIDE = 0
_INFINITE = 0xFFFFFFFF
_ERROR_CANCELLED = 1223
_TH32CS_SNAPPROCESS = 0x2
# Fast while the launcher lives — a hand-off launcher can start its copy
# and exit in well under half a second — slower once it's gone.
_POLL_FAST, _POLL_SLOW = 0.1, 0.5
# Names installers give the temp copy they hand off to: Inno Setup's
# _iu*.tmp (any .tmp image), NSIS's Au_.exe / Un_A.exe.
_HANDOFF_NAME = re.compile(r"\.tmp$|^au_\.exe$|^un_a\.exe$", re.IGNORECASE)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def split_command(command_line: str) -> list[str]:
    """Split a registry UninstallString into argv.

    Windows command-line quoting is its own dialect (`shlex` gets backslashes
    wrong), and the OS ships the exact parser every program uses to read its
    own arguments: CommandLineToArgvW.
    """
    # Declared, not left to ctypes' default: an undeclared restype is a C int,
    # which turned the returned LPWSTR* into a plain (truncated) integer and
    # crashed every registry uninstall before it started.
    to_argv = ctypes.windll.shell32.CommandLineToArgvW
    to_argv.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
    argc = ctypes.c_int()
    argv = to_argv(command_line, ctypes.byref(argc))
    if not argv:
        return []
    try:
        return [argv[i] for i in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(argv, ctypes.c_void_p))


def elevated_cmd_params(argv: list[str], log: Path) -> str:
    """cmd.exe's parameters for running `argv` with its output sent to `log`.

    The quotes wrap everything *after* `/c`: cmd then strips just the outer
    pair and runs the rest as typed. Quoting the whole thing including `/c`
    broke every elevated uninstall — a program under `C:\\Program Files`
    came out as "'C:\\Program' is not recognized", and switches were lost.
    """
    return f'/c "{subprocess.list2cmdline(argv)} > "{log}" 2>&1"'


def family_of(
    root: int, processes: dict[int, tuple[int, str]], known: set[int],
    baseline: frozenset = frozenset(),
) -> set[int]:
    """`known` plus `root` plus every process descended from any of them.

    Pure: `processes` is pid -> (parent pid, image name). Dead members stay in
    the set, so a grandchild is still found after its parent has exited —
    parent pids survive the parent, which is what makes a hand-off traceable.

    That needs the parent to have been seen alive at least once. A launcher
    that spawns its copy and exits between two polls breaks the chain, so an
    installer temp copy (`_HANDOFF_NAME`) that wasn't running before launch
    (`baseline`) and whose parent is already gone is adopted as well.
    """
    parents = {pid: parent for pid, (parent, _name) in processes.items()}
    family = set(known) | {root}
    family |= {
        pid for pid, (parent, name) in processes.items()
        if pid not in baseline and parent not in processes and _HANDOFF_NAME.search(name)
    }
    while True:
        new = {pid for pid, parent in parents.items() if parent in family} - family
        if not new:
            return family
        family |= new


def _process_table() -> dict[int, tuple[int, str]]:
    """pid -> (parent pid, image name) for every running process, elevated
    ones included (a Toolhelp32 snapshot needs no access to the processes)."""
    from ctypes import wintypes

    class _ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    k = ctypes.windll.kernel32
    k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p  # a HANDLE, not an int
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    snapshot = k.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, ctypes.c_void_p(-1).value):
        return {}
    entry = _ProcessEntry()
    entry.dwSize = ctypes.sizeof(entry)
    table = {}
    try:
        more = k.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
            more = k.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        k.CloseHandle(snapshot)
    return table


def _wait_for_family(root: int, root_done, done=None, baseline=frozenset()) -> None:
    """Wait until `root` and everything it started have exited, or `done()`.

    Uninstallers commonly hand off and exit: Inno Setup copies itself to
    %TEMP% (_iu*.tmp), NSIS to Au_.exe, and the copy does the removal — and
    asks "are you sure?" — after the process we launched is gone. Waiting on
    that process alone reported IObit's uninstall as finished (and failed)
    while its own prompt was still on screen.

    `done` lets the caller stop early once the job is verifiably done (the
    app's registry entry is gone), so a browser page the uninstaller opened
    on its way out doesn't hold the wait open. ponytail: a reused pid can
    adopt an unrelated process into the family; the wait then ends when that
    process exits or at `done()`.
    """
    family = {root}
    while True:
        processes = _process_table()
        family = family_of(root, processes, family, baseline)
        if not root_done():
            time.sleep(_POLL_FAST)
            continue
        if not (family - {root}) & processes.keys():
            return
        if done is not None and done():
            return
        time.sleep(_POLL_SLOW)


def _run_elevated(argv: list[str], follow: bool = False, done=None) -> tuple[int, str]:
    """Launch through UAC and wait for it.

    An elevated process runs at a higher integrity level than this one, so it
    can't inherit our pipes — output has to come back through a file both
    sides can reach. Hence the `cmd /c … > file` wrapper rather than
    capture_output.
    """
    from ctypes import wintypes  # Windows-only module; kept out of import time
                                 # so the pure parsers stay testable anywhere.

    class _ShellExecuteInfoW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HANDLE),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    # A process left running after an early `done()` may still hold the log
    # open; failing to delete a temp file must not fail the uninstall.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        log = Path(tmp, "output.txt")

        info = _ShellExecuteInfoW()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = _SEE_MASK_NOCLOSEPROCESS | _SEE_MASK_NO_CONSOLE
        info.lpVerb = "runas"
        info.lpFile = "cmd.exe"
        info.lpParameters = elevated_cmd_params(argv, log)
        info.nShow = _SW_HIDE

        baseline = frozenset(_process_table()) if follow else frozenset()
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
            code = ctypes.get_last_error() or ctypes.GetLastError()
            if code == _ERROR_CANCELLED:
                return 1, "Cancelled at the Windows permission prompt."
            return 1, f"Could not start the uninstaller with administrator rights (error {code})."

        k = ctypes.windll.kernel32
        k.WaitForSingleObject.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        k.GetProcessId.argtypes = [ctypes.c_void_p]
        process = info.hProcess
        if follow:
            _wait_for_family(
                k.GetProcessId(process), lambda: k.WaitForSingleObject(process, 0) == 0,
                done, baseline,
            )
        k.WaitForSingleObject(process, _INFINITE)
        exit_code = wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(info.hProcess)
        output = ""
        if log.exists():
            with log.open(newline="", errors="replace") as f:  # newline="": keep the \r clean_output looks for
                output = clean_output(f.read())
        return exit_code.value, output


def clean_output(text: str) -> str:
    """What a console would show: sfc writes UTF-16, which arrives with a NUL
    after every letter, and progress lines ("Verification 45% complete")
    redraw themselves after a carriage return, of which only the last counts."""
    return re.sub(r"[^\r\n]*\r(?!\n)", "", text.replace("\x00", "")).strip()


def tail(text: str, lines: int = 4) -> str:
    """The end of a failed command's output, where its reason is."""
    return "\n".join(text.strip().splitlines()[-lines:])


def run(argv: list[str], elevated: bool = False, on_line=None, encoding=None, follow: bool = False,
        done=None) -> tuple[int, str]:
    """Run a command, with or without a UAC prompt. Returns (exit code, output).

    `follow` also waits for every process the command starts (uninstallers
    that hand off to a copy of themselves — see `_wait_for_family`), until
    they exit or `done()` says the work is verifiably finished.

    On success `output` is stdout, on failure it's stderr — a scan needs the
    former (PowerShell happily writes warnings to stderr while returning
    perfectly good data on stdout) and a failed uninstall needs the latter.
    With `on_line`, each line goes there as it's printed (stdout and stderr
    together, in order: whoever watches wants all of it). An elevated
    command's output only exists once it has finished, so it comes all at once.
    """
    if elevated and not is_admin():
        code, output = _run_elevated(argv, follow, done)
        for line in output.splitlines() if on_line else ():
            on_line(line)
        return code, output
    if on_line:
        return _stream(argv, on_line, encoding)
    try:
        baseline = frozenset(_process_table()) if follow else frozenset()
        process = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
            creationflags=_NO_WINDOW, encoding=encoding, errors="replace",
        )
    except OSError as exc:
        # The tool isn't installed or isn't on PATH. Returned rather than
        # raised: this runs on a worker thread, and an exception here would
        # kill the thread before it could re-enable the window.
        return 1, f"Could not run {argv[0]}: {exc}"
    stdout, stderr = process.communicate()
    if follow:  # the launcher is done; its hand-off copy may not be
        _wait_for_family(process.pid, lambda: True, done, baseline)
    if process.returncode == 0:
        return 0, (stdout or "").strip()
    return process.returncode, (stderr or stdout or "").strip()


def _stream(argv: list[str], on_line, encoding=None) -> tuple[int, str]:
    try:
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   text=True, creationflags=_NO_WINDOW, encoding=encoding, errors="replace")
    except OSError as exc:
        return 1, f"Could not run {argv[0]}: {exc}"
    lines = []
    for line in process.stdout:
        line = line.replace("\x00", "").rstrip()
        if line:
            lines.append(line)
            on_line(line)
    return process.wait(), "\n".join(lines)


def powershell(script: str, elevated: bool = False, on_line=None) -> tuple[int, str]:
    shell = ["powershell", "-NoProfile", "-NonInteractive"]
    if elevated and not is_admin():
        # An elevated command travels through cmd /c, whose quoting knows
        # nothing of PowerShell's; base64 has nothing left to quote.
        encoded = base64.b64encode(script.encode("utf-16-le")).decode()
        return run([*shell, "-EncodedCommand", encoded], elevated=True, on_line=on_line)
    return run([*shell, "-Command", script], on_line=on_line)
