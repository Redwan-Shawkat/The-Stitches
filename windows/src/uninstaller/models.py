"""Shared data types. No IO here — see backends/ and risk.py for that.

Same shape as the Linux build's models.py; only `Source` differs, because
"how did this get onto the machine" has different answers on Windows.
"""

from dataclasses import dataclass, field
from enum import Enum


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class Source(str, Enum):
    INSTALLER = "Installer (MSI/EXE)"
    STORE = "Microsoft Store"
    CHOCOLATEY = "Chocolatey"
    SCOOP = "Scoop"


class Risk(str, Enum):
    SAFE = "Safe"
    CAUTION = "Caution"
    CRITICAL = "Critical"


@dataclass
class App:
    """One installed thing, from any source."""

    name: str
    id: str  # registry key, package full name, or choco/scoop package name
    source: Source
    version: str = ""
    size_bytes: int = 0
    is_system: bool = False
    risk: Risk = Risk.SAFE
    risk_reason: str = ""
    # backend-specific data uninstall() needs (uninstall command, install
    # scope — machine-wide installs need elevation, per-user ones don't)
    extra: dict = field(default_factory=dict)

    @property
    def size_human(self) -> str:
        return format_size(self.size_bytes)
