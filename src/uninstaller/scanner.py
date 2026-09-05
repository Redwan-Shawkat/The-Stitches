"""Aggregates every backend into one list. A backend whose underlying tool
isn't installed (e.g. no Wine on this machine) just contributes nothing
instead of crashing the whole scan."""

from .backends.apt_backend import AptBackend
from .backends.flatpak_backend import FlatpakBackend
from .backends.snap_backend import SnapBackend
from .backends.wine_backend import WineBackend
from .models import App, Source

_BY_SOURCE = {
    Source.APT: AptBackend(),
    Source.SNAP: SnapBackend(),
    Source.FLATPAK: FlatpakBackend(),
    Source.WINE: WineBackend(),
}


def scan_all() -> list[App]:
    apps: list[App] = []
    for backend in _BY_SOURCE.values():
        try:
            apps.extend(backend.scan())
        except OSError:
            continue  # underlying tool (dpkg/snap/flatpak/wine) not installed here
    return sorted(apps, key=lambda a: a.name.lower())


def backend_for(app: App):
    return _BY_SOURCE[app.source]
