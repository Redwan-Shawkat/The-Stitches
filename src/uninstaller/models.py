"""Shared data types. No IO here — see backends/ and risk.py for that."""

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
    APT = "Terminal / .deb"
    SNAP = "Snap Store"
    FLATPAK = "Flatpak"
    WINE = "Wine (Windows app)"


class Risk(str, Enum):
    SAFE = "Safe"
    CAUTION = "Caution"
    CRITICAL = "Critical"


@dataclass
class App:
    """One installed thing, from any source."""

    name: str
    id: str  # package/snap/flatpak name, or wine prefix path + registry key
    source: Source
    version: str = ""
    size_bytes: int = 0
    is_system: bool = False
    risk: Risk = Risk.SAFE
    risk_reason: str = ""
    # backend-specific data uninstall() needs (e.g. wine prefix + uninstall string)
    extra: dict = field(default_factory=dict)

    @property
    def size_human(self) -> str:
        return format_size(self.size_bytes)
