"""Aggregates every backend into one list. A backend whose underlying tool
isn't installed (no Chocolatey, no Scoop on this machine) just contributes
nothing instead of crashing the whole scan."""

from .backends.choco_backend import ChocoBackend
from .backends.registry_backend import RegistryBackend
from .backends.scoop_backend import ScoopBackend
from .backends.store_backend import StoreBackend
from .models import App, Source

_BY_SOURCE = {
    Source.INSTALLER: RegistryBackend(),
    Source.STORE: StoreBackend(),
    Source.CHOCOLATEY: ChocoBackend(),
    Source.SCOOP: ScoopBackend(),
}


def scan_all() -> list[App]:
    apps: list[App] = []
    for backend in _BY_SOURCE.values():
        try:
            apps.extend(backend.scan())
        except OSError:
            continue  # underlying tool (powershell/choco/scoop) not present here
    return sorted(apps, key=lambda a: a.name.lower())


def backend_for(app: App):
    return _BY_SOURCE[app.source]
