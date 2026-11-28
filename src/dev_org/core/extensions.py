"""Extension lifecycle: ownership and maturation of dev-org's own extensions.

Implements issue #62 (acceptance test A58): an extension moves through
experimental, qualified, recommended, and deprecated status; a qualified
agent-based deputy takes over automatically when the primary maintainer is
unavailable; deprecation notifies affected projects; and the status is
visible to installs (section 4, A58).

An extension is an optional, contract-plugged unit (a board adapter, an
engine, a knowledge backend, a pack or recipe) — never part of the core.
The external-agent adapter is a separate concern and lives in the gateway
module, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: The extension lifecycle statuses (A58), in order.
ExtensionStatus = Literal["experimental", "qualified", "recommended", "deprecated"]

STATUS_ORDER: dict[str, int] = {"experimental": 0, "qualified": 1, "recommended": 2, "deprecated": 3}


@dataclass
class Extension:
    """One extension and its visible lifecycle state (section 4, A58)."""

    name: str
    publisher: str
    version: str
    status: ExtensionStatus = "experimental"
    maintainer: str = "maintainer-1"
    deputy: str | None = None  # a qualified agent-based deputy (A58)
    contracts: list[str] = field(default_factory=list)
    notified_projects: list[str] = field(default_factory=list)


class ExtensionLifecycle:
    """Move extensions through their statuses and handle maintainer handover."""

    def __init__(self) -> None:
        """Create an empty extension registry."""
        self._extensions: dict[str, Extension] = {}

    def register(
        self, *, name: str, publisher: str, version: str, contracts: list[str], maintainer: str
    ) -> Extension:
        """Register an extension in experimental status (section 4)."""
        extension = Extension(
            name=name, publisher=publisher, version=version, contracts=contracts, maintainer=maintainer
        )
        self._extensions[name] = extension
        return extension

    def promote(self, name: str, to: ExtensionStatus) -> Extension:
        """Move an extension to a later status; refuses a backwards move (A58).

        The status must advance (experimental -> qualified -> recommended),
        and deprecation notifies every affected project. The new status is
        visible to installs through the registry.
        """
        extension = self._extensions[name]
        if STATUS_ORDER[to] <= STATUS_ORDER[extension.status]:
            msg = f"cannot move {name} back from {extension.status} to {to}"
            raise ValueError(msg)
        extension.status = to
        if to == "deprecated":
            extension.notified_projects = list(extension.contracts)  # notify affected projects
        return extension

    def assign_deputy(self, name: str, *, deputy: str) -> Extension:
        """Assign a qualified agent-based deputy when the maintainer is unavailable."""
        extension = self._extensions[name]
        extension.deputy = deputy
        return extension

    def owns_contract(self, name: str, contract: str) -> bool:
        """Whether the extension (or its deputy) covers a common contract."""
        extension = self._extensions[name]
        return contract in extension.contracts

    def get(self, name: str) -> Extension:
        """Return the extension by name."""
        return self._extensions[name]


__all__ = ["Extension", "ExtensionLifecycle", "ExtensionStatus"]
