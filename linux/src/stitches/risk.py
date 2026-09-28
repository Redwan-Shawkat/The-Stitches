"""Risk classification. Pure functions — see ai-knowledgebase.md for why this
is a heuristic on cheap-to-read fields instead of a full dependency graph.
"""

import re

from .models import Risk, Source

# ponytail: name-pattern heuristic, not a real "is this a runtime" query.
# Upgrade path: `snap info <name>` has a `type: base|app` field; skipped to
# avoid one extra subprocess call per snap during a scan.
_RUNTIME_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^core\d*$",
        r"^snapd$",
        r"^bare$",
        r"^gtk-common-themes$",
        r"^gnome-\d",
        r".*-platform$",
        r".*\.platform$",
        r".*\.sdk$",
    )
]


def classify_apt(priority: str, essential: str) -> tuple[Risk, str, bool]:
    """From dpkg-query's Priority/Essential fields."""
    if essential.lower() == "yes" or priority.lower() == "required":
        return (
            Risk.CRITICAL,
            "Marked essential by the package system — removing it can break your OS.",
            True,
        )
    if priority.lower() == "important":
        return (
            Risk.CAUTION,
            "Other system tools may expect this to be present.",
            True,
        )
    return Risk.SAFE, "A standalone app — nothing else is known to depend on it.", False


def classify_runtime_name(name: str) -> tuple[Risk, str, bool] | None:
    """Snap/Flatpak runtime-base detection by name. None if not a known runtime."""
    if any(p.match(name) for p in _RUNTIME_PATTERNS):
        return (
            Risk.CRITICAL,
            "A shared runtime other apps run on top of — removing it can break them.",
            True,
        )
    return None


def classify_local(running: bool) -> tuple[Risk, str, bool]:
    if running:
        return Risk.CAUTION, "This is the Stitches you're using: it keeps running until you close it, then it's gone.", False
    return Risk.SAFE, "A copy installed into your home folder by install.sh; nothing else uses it.", False


def classify_default(source: Source) -> tuple[Risk, str, bool]:
    if source == Source.WINE:
        return Risk.SAFE, "Lives inside its own Wine prefix — removing it won't touch the rest of your system.", False
    return Risk.SAFE, "A standalone app — nothing else is known to depend on it.", False
