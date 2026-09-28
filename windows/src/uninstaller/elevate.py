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
from pathlib import Path

# Keeps a console window from flashing up behind every scan/uninstall call —
# this is a --windowed build, so there's no console to reuse.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SEE_MASK_NO_CONSOLE = 0x00008000
_SW_HIDE = 0
_INFINITE = 0xFFFFFFFF
_ERROR_CANCELLED = 1223


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
    argc = ctypes.c_int()
    argv = ctypes.windll.shell32.CommandLineToArgvW(command_line, ctypes.byref(argc))
    if not argv:
        return []
    try:
        return [ctypes.wstring_at(argv[i]) for i in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


def _run_elevated(argv: list[str]) -> tuple[int, str]:
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

    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp, "output.txt")
        inner = subprocess.list2cmdline(argv)
        params = f'/c {inner} > "{log}" 2>&1'

        info = _ShellExecuteInfoW()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = _SEE_MASK_NOCLOSEPROCESS | _SEE_MASK_NO_CONSOLE
        info.lpVerb = "runas"
        info.lpFile = "cmd.exe"
        info.lpParameters = f'"{params}"'
        info.nShow = _SW_HIDE

        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
            code = ctypes.get_last_error() or ctypes.GetLastError()
            if code == _ERROR_CANCELLED:
                return 1, "Cancelled at the Windows permission prompt."
            return 1, f"Could not start the uninstaller with administrator rights (error {code})."

        ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, _INFINITE)
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


def run(argv: list[str], elevated: bool = False, on_line=None, encoding=None) -> tuple[int, str]:
    """Run a command, with or without a UAC prompt. Returns (exit code, output).

    On success `output` is stdout, on failure it's stderr — a scan needs the
    former (PowerShell happily writes warnings to stderr while returning
    perfectly good data on stdout) and a failed uninstall needs the latter.
    With `on_line`, each line goes there as it's printed (stdout and stderr
    together, in order: whoever watches wants all of it). An elevated
    command's output only exists once it has finished, so it comes all at once.
    """
    if elevated and not is_admin():
        code, output = _run_elevated(argv)
        for line in output.splitlines() if on_line else ():
            on_line(line)
        return code, output
    if on_line:
        return _stream(argv, on_line, encoding)
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
            creationflags=_NO_WINDOW, encoding=encoding, errors="replace",
        )
    except OSError as exc:
        # The tool isn't installed or isn't on PATH. Returned rather than
        # raised: this runs on a worker thread, and an exception here would
        # kill the thread before it could re-enable the window.
        return 1, f"Could not run {argv[0]}: {exc}"
    if result.returncode == 0:
        return 0, (result.stdout or "").strip()
    return result.returncode, (result.stderr or result.stdout or "").strip()


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
