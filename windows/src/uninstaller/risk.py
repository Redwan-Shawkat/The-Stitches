"""Risk classification. Pure functions — see ai-knowledgebase.md for why this
is a heuristic on fields the scan already has in hand instead of a real
dependency graph.
"""

import re

from .models import Risk, Source


def _patterns(*sources):
    return [re.compile(p, re.IGNORECASE) for p in sources]


# ponytail: name/field heuristic, not a real "what depends on this" query.
# Windows has no reverse-dependency database to ask — the closest thing is
# reading every other app's imports, which is not a scan-time operation.
_DRIVER_PATTERNS = _patterns(
    r"\bdriver(s)?\b",
    r"^intel\b.*\b(chipset|management|graphics)\b",
    r"^nvidia\b",
    r"^amd\b.*\b(software|chipset)\b",
    r"^realtek\b",
)
_RUNTIME_PATTERNS = _patterns(
    r"visual c\+\+.*redistributable",
    r"\.net.*(runtime|framework|desktop runtime)",
    r"edge.*webview2",
    r"windows (software development kit|driver kit)",
    r"\bdirectx\b",
    r"java.*(runtime|development kit)",
    r"\bvcredist\b",
)
# MSIX/Appx packages that are Windows itself rather than apps the user chose.
_SYSTEM_APPX_PATTERNS = _patterns(
    r"^microsoft\.windows\.",
    r"^microsoftwindows\.",
    r"^microsoft\.ui\.xaml",
    r"^microsoft\.vclibs",
    r"^microsoft\.net\.",
    r"^microsoft\.services\.store",
    r"^windows\.",
    r"^microsoft\.aad\.brokerplugin$",
    r"^microsoft\.accountscontrol$",
)
# The package managers themselves: removing one orphans everything it installed.
_MANAGER_NAMES = {"chocolatey", "chocolatey-core.extension", "scoop", "main", "extras"}


def classify_installer(
    name: str, system_component: bool, release_type: str
) -> tuple[Risk, str, bool]:
    """From the registry Uninstall key's own values — no extra lookups."""
    if system_component:
        return (
            Risk.CRITICAL,
            "Windows hides this from Apps & Features because other software "
            "installed it and depends on it.",
            True,
        )
    if release_type.lower() == "driver" or any(p.search(name) for p in _DRIVER_PATTERNS):
        return (
            Risk.CRITICAL,
            "A hardware driver — removing it can stop the device it runs from working.",
            True,
        )
    if any(p.search(name) for p in _RUNTIME_PATTERNS):
        return (
            Risk.CAUTION,
            "A shared runtime other programs are built against — they stop "
            "launching if it goes.",
            True,
        )
    return Risk.SAFE, "A standalone app — nothing else is known to depend on it.", False


def classify_store_package(
    name: str, is_framework: bool, non_removable: bool
) -> tuple[Risk, str, bool]:
    """Appx/MSIX. `IsFramework` is Microsoft's own word for "a runtime other
    packages bind to", which is exactly the distinction we need."""
    if is_framework:
        return (
            Risk.CRITICAL,
            "A shared framework package other Store apps run on top of — "
            "removing it can break them.",
            True,
        )
    if non_removable or any(p.match(name) for p in _SYSTEM_APPX_PATTERNS):
        return (
            Risk.CRITICAL,
            "Part of Windows itself, not an app you installed.",
            True,
        )
    return Risk.SAFE, "A sandboxed Store app — removing it doesn't affect other apps.", False


def classify_managed_package(name: str, source: Source) -> tuple[Risk, str, bool]:
    """Chocolatey/Scoop packages. The manager's own package is the one thing
    here that isn't safe to remove casually."""
    if name.lower() in _MANAGER_NAMES:
        return (
            Risk.CRITICAL,
            "The package manager itself — removing it leaves everything it "
            "installed with no way to update or uninstall.",
            True,
        )
    if source == Source.SCOOP:
        return (
            Risk.SAFE,
            "Lives inside your Scoop directory — removing it won't touch the "
            "rest of your system.",
            False,
        )
    return Risk.SAFE, "A standalone package — nothing else is known to depend on it.", False
