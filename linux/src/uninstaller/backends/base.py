"""Common backend shape. Four real implementations share this — that's what
earns the shared shape (ponytail: no interface for a single implementation)."""

from typing import Protocol

from ..models import App


class Backend(Protocol):
    def scan(self) -> list[App]: ...

    def uninstall(self, app: App) -> tuple[bool, str]:
        """Returns (success, message)."""
        ...
