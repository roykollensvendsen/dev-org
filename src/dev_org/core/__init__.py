"""Core module: plans from the board, distributes work, manages reservations.

The organization core knows the agent adapter's contract, not the engine's
internal protocol (section 3.1). It owns the use case and asks the gateway
for external changes; it never calls a board, Git, CI, or other external
target directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dev_org.state.models import Reservation, Task


@runtime_checkable
class Scheduler(Protocol):
    """How the core picks work and hands it to a worker."""

    def assign(self, task: Task) -> Reservation | None:
        """Reserve the task for a worker, or return None if none is ready."""
        ...


@runtime_checkable
class WorkQueue(Protocol):
    """The durable queue of ready work."""

    def next_ready(self, project_id: str) -> Task | None:
        """Return the next ready task for a project, or None if the queue is empty."""
        ...


__all__ = ["Scheduler", "WorkQueue"]
