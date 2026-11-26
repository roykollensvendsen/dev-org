"""Execution environment module: create, inspect, and end isolated runs.

The execution environment (section 3.3) creates and ends isolated
workspaces and processes, and enforces access to files, network, and local
resources. This module defines the contract; the rootless Podman backend is
issue #7.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ExecutionBackend(Protocol):
    """Create, inspect, and end an isolated execution environment."""

    def create(self, profile: dict[str, object]) -> str:
        """Create a runtime from a profile and return its runtime ID."""
        ...

    def inspect(self, runtime_id: str) -> dict[str, object]:
        """Report the runtime's current state and resource use."""
        ...

    def end(self, runtime_id: str) -> None:
        """End the runtime and confirm it has stopped."""
        ...


__all__ = ["ExecutionBackend"]
