"""Wine backend. Wine keeps no central app database — each prefix has its own
system.reg/user.reg (plain-text registry dumps). We read the same
Uninstall\\<key> subtree Wine's own `wine uninstaller` GUI reads, straight
from the file, instead of shelling out to spin up a Wine process just to list
apps. See ai-knowledgebase.md."""

import os
import re
import subprocess
from pathlib import Path

from ..models import App, Source
from ..risk import classify_default

_SECTION_RE = re.compile(r"^\[(.+)\]\s*\d*\s*$")
_UNINSTALL_KEY_RE = re.compile(r"Uninstall\\\\([^\\\]]+)$", re.IGNORECASE)
_STRING_KV_RE = re.compile(r'^"([^"]+)"="(.*)"$')
_DWORD_KV_RE = re.compile(r'^"([^"]+)"=dword:([0-9a-fA-F]+)$')

_PREFIX_GLOBS = (
    "~/.wine",
    "~/.local/share/wineprefixes/*",
    "~/.PlayOnLinux/wineprefix/*",
)


def find_prefixes() -> list[Path]:
    found = []
    for pattern in _PREFIX_GLOBS:
        expanded = Path(pattern.replace("~", str(Path.home())))
        candidates = [expanded] if "*" not in pattern else list(expanded.parent.glob(expanded.name))
        for prefix in candidates:
            if (prefix / "system.reg").is_file():
                found.append(prefix)
    env_prefix = os.environ.get("WINEPREFIX")
    if env_prefix and Path(env_prefix, "system.reg").is_file():
        found.append(Path(env_prefix))
    return found


def _unescape(value: str) -> str:
    out, i = [], 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in ("\\", '"'):
            out.append(value[i + 1])
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def parse_uninstall_keys(text: str) -> list[dict]:
    """Pure parse of a system.reg/user.reg file's Uninstall subkeys."""
    entries: list[dict] = []
    current_key = None
    current: dict = {}

    def flush():
        if current_key and current.get("DisplayName"):
            entries.append(
                {
                    "key": current_key,
                    "name": current["DisplayName"],
                    "version": current.get("DisplayVersion", ""),
                    "uninstall_string": current.get("UninstallString", ""),
                    "size_bytes": int(current.get("EstimatedSize", 0)) * 1024,
                }
            )

    for line in text.splitlines():
        section = _SECTION_RE.match(line)
        if section:
            flush()
            current = {}
            key_match = _UNINSTALL_KEY_RE.search(section.group(1))
            current_key = key_match.group(1) if key_match else None
            continue
        if current_key is None:
            continue
        kv = _STRING_KV_RE.match(line)
        if kv:
            current[kv.group(1)] = _unescape(kv.group(2))
            continue
        dw = _DWORD_KV_RE.match(line)
        if dw:
            current[dw.group(1)] = int(dw.group(2), 16)
    flush()
    return entries


def build_apps(prefix: Path, entries: list[dict]) -> list[App]:
    risk, reason, is_system = classify_default(Source.WINE)
    apps = []
    for entry in entries:
        apps.append(
            App(
                name=entry["name"],
                id=f"{prefix}::{entry['key']}",
                source=Source.WINE,
                version=entry["version"],
                size_bytes=entry["size_bytes"],
                is_system=is_system,
                risk=risk,
                risk_reason=reason,
                extra={"prefix": str(prefix), "uninstall_string": entry["uninstall_string"]},
            )
        )
    return apps


class WineBackend:
    def scan(self) -> list[App]:
        apps = []
        for prefix in find_prefixes():
            seen_keys = set()
            entries = []
            for reg_file in ("system.reg", "user.reg"):
                path = prefix / reg_file
                if not path.is_file():
                    continue
                for entry in parse_uninstall_keys(path.read_text(errors="replace")):
                    if entry["key"] not in seen_keys:
                        seen_keys.add(entry["key"])
                        entries.append(entry)
            apps.extend(build_apps(prefix, entries))
        return apps

    def uninstall(self, app: App) -> tuple[bool, str]:
        uninstall_string = app.extra.get("uninstall_string")
        if not uninstall_string:
            return False, "No uninstaller registered for this app in Wine's registry."
        env = dict(os.environ, WINEPREFIX=app.extra["prefix"])
        result = subprocess.run(
            ["wine", "cmd", "/c", uninstall_string],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0, (result.stderr or result.stdout).strip()
