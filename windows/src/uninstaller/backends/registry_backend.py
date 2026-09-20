"""Registry backend: everything installed by an MSI or an EXE installer.

This is the Windows counterpart to the Linux build's apt/dpkg backend — the
"a program put itself on this machine the normal way" source. The list lives
in the Uninstall key, the same place Apps & Features reads, and `winreg` is
stdlib, so nothing is shelled out to scan. See ai-knowledgebase.md for why
all three registry views are walked and why hidden entries are shown here
even though Windows hides them.
"""

import re

from ..elevate import run, split_command
from ..models import App, Source
from ..risk import classify_installer

try:
    import winreg
except ImportError:  # not Windows — the pure functions below still work
    winreg = None

_SUBKEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
_GUID_RE = re.compile(r"^\{[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}\}$")
# Patches, not programs. Apps & Features files these under "Installed Updates";
# listing them next to real apps would bury the apps.
_PATCH_RELEASE_TYPES = {"update", "security update", "hotfix", "servicepack"}


def is_listable(entry: dict) -> bool:
    """An Uninstall key is a real installed program, not a patch or a stub."""
    if not entry.get("name"):
        return False
    if entry.get("parent"):  # a patch to another product, which owns removal
        return False
    return entry.get("release_type", "").lower() not in _PATCH_RELEASE_TYPES


def uninstall_command_line(entry: dict) -> str:
    """Which command actually removes this entry.

    Preference order matters: a program that advertises a silent uninstall
    should get one; an MSI's own UninstallString is usually `MsiExec /I{GUID}`
    (/I opens the interactive repair-or-remove dialog), so it's rewritten to a
    real quiet removal rather than used as-is.
    """
    if entry.get("quiet_uninstall_string"):
        return entry["quiet_uninstall_string"]
    if entry.get("windows_installer") and _GUID_RE.match(entry.get("key", "")):
        return f'msiexec /x {entry["key"]} /qn /norestart'
    return entry.get("uninstall_string", "")


def build_apps(entries: list[dict]) -> list[App]:
    apps = []
    for entry in entries:
        if not is_listable(entry):
            continue
        risk, reason, is_system = classify_installer(
            entry["name"], entry.get("system_component", False), entry.get("release_type", "")
        )
        apps.append(
            App(
                name=entry["name"],
                id=entry.get("key", entry["name"]),
                source=Source.INSTALLER,
                version=entry.get("version", ""),
                size_bytes=entry.get("size_bytes", 0),
                is_system=is_system,
                risk=risk,
                risk_reason=reason,
                extra={
                    "scope": entry.get("scope", "machine"),
                    "command": uninstall_command_line(entry),
                    "publisher": entry.get("publisher", ""),
                },
            )
        )
    return apps


def _value(key, name, default=None):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def _read_view(root, access, scope: str) -> list[dict]:
    entries = []
    try:
        base = winreg.OpenKey(root, _SUBKEY, 0, winreg.KEY_READ | access)
    except OSError:
        return entries
    with base:
        for i in range(winreg.QueryInfoKey(base)[0]):
            try:
                name = winreg.EnumKey(base, i)
                with winreg.OpenKey(base, name) as key:
                    entries.append(
                        {
                            "key": name,
                            "scope": scope,
                            "name": str(_value(key, "DisplayName", "") or "").strip(),
                            "version": str(_value(key, "DisplayVersion", "") or ""),
                            "publisher": str(_value(key, "Publisher", "") or ""),
                            "uninstall_string": str(_value(key, "UninstallString", "") or ""),
                            "quiet_uninstall_string": str(
                                _value(key, "QuietUninstallString", "") or ""
                            ),
                            "size_bytes": int(_value(key, "EstimatedSize", 0) or 0) * 1024,
                            "system_component": bool(_value(key, "SystemComponent", 0)),
                            "release_type": str(_value(key, "ReleaseType", "") or ""),
                            "windows_installer": bool(_value(key, "WindowsInstaller", 0)),
                            "parent": str(_value(key, "ParentKeyName", "") or ""),
                        }
                    )
            except OSError:
                continue  # key vanished mid-enumeration (an install finishing)
    return entries


def read_uninstall_entries() -> list[dict]:
    """All three views: 64-bit, 32-bit (WOW6432Node), and per-user."""
    entries = _read_view(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY, "machine")
    entries += _read_view(winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY, "machine")
    entries += _read_view(winreg.HKEY_CURRENT_USER, 0, "user")
    return entries


class RegistryBackend:
    def scan(self) -> list[App]:
        if winreg is None:
            return []
        return build_apps(read_uninstall_entries())

    def uninstall(self, app: App) -> tuple[bool, str]:
        command = app.extra.get("command", "")
        if not command:
            return False, "This program registered no uninstaller with Windows."
        argv = split_command(command)
        if not argv:
            return False, f"Could not read this program's uninstall command: {command}"
        # A per-machine program writes under Program Files and HKLM, so its
        # uninstaller needs administrator rights (CLAUDE.md non-negotiable:
        # that consent prompt is Windows', not ours). Per-user installs don't.
        code, output = run(argv, elevated=app.extra.get("scope") == "machine")
        if code == 0:
            return True, ""
        # 1605 = "this action is only valid for installed products": the MSI is
        # already gone, so the files are too — same reasoning as the Linux
        # build trusting dpkg's status over a failing postrm's exit code.
        if code == 1605:
            return True, "Windows reported it was already removed."
        return False, output or f"The uninstaller exited with code {code}."
