"""Durable store: the persistence port and a deterministic in-memory adapter.

The persistence port (specification 10.1) covers transactional writes,
idempotency, reservations, the queue, inbox/outbox, and consistent reads.
This module defines the operations the core needs and provides a
deterministic in-memory implementation for development and contract tests;
a PostgreSQL adapter implements the same port later.

The in-memory store is a test double, not evidence of multi-worker
capacity (acceptance test A73 says so explicitly). It is durable only for
the lifetime of the process, which is exactly what the simulated-worker
tests in issue #5 need: a "restart" is a fresh store-backed service, and a
fresh service must recover the preserved state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dev_org.state.models import Attempt, CiWaitCondition, Event, Reservation, Task


@runtime_checkable
class Store(Protocol):
    """The durable-state operations the core relies on."""

    def save_task(self, task: Task) -> None:
        """Persist a task, replacing any previous version of the same ID."""
        ...

    def get_task(self, task_id: str) -> Task | None:
        """Return the task with that ID, or None if it is not stored."""
        ...

    def save_attempt(self, attempt: Attempt) -> None:
        """Persist an attempt, replacing any previous version of the same ID."""
        ...

    def get_attempt(self, attempt_id: str) -> Attempt | None:
        """Return the attempt with that ID, or None if it is not stored."""
        ...

    def attempts_for_task(self, task_id: str) -> list[Attempt]:
        """Return every attempt recorded for a task, oldest first."""
        ...

    def save_reservation(self, reservation: Reservation) -> None:
        """Persist the current reservation for an attempt, replacing the old one."""
        ...

    def get_reservation(self, attempt_id: str) -> Reservation | None:
        """Return the current reservation for an attempt, or None."""
        ...

    def append_event(self, event: Event) -> None:
        """Append an event to the append-only log."""
        ...

    def events_for_task(self, task_id: str) -> list[Event]:
        """Return every event recorded for a task, in order."""
        ...

    def save_wait_condition(self, condition: CiWaitCondition) -> None:
        """Persist a wait condition, replacing any previous version for its task."""
        ...

    def get_wait_condition(self, task_id: str) -> CiWaitCondition | None:
        """Return the stored wait condition for a task, or None."""
        ...

    def ready_tasks(self, project_id: str) -> list[Task]:
        """Return the ready tasks for a project."""
        ...


@dataclass
class InMemoryStore:
    """A deterministic store for tests: nothing survives the process.

    ``attempts`` is keyed by attempt ID; ``reservations`` by attempt ID;
    ``events`` is an append-only list. All reads are consistent within a
    call because nothing is concurrent here.
    """

    tasks: dict[str, Task] = field(default_factory=dict)
    attempts: dict[str, Attempt] = field(default_factory=dict)
    reservations: dict[str, Reservation] = field(default_factory=dict)
    wait_conditions: dict[str, CiWaitCondition] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)

    def save_task(self, task: Task) -> None:
        """Store a task under its ID."""
        self.tasks[task.id] = task

    def get_task(self, task_id: str) -> Task | None:
        """Return the stored task, or None."""
        return self.tasks.get(task_id)

    def save_attempt(self, attempt: Attempt) -> None:
        """Store an attempt under its ID."""
        self.attempts[attempt.id] = attempt

    def get_attempt(self, attempt_id: str) -> Attempt | None:
        """Return the stored attempt, or None."""
        return self.attempts.get(attempt_id)

    def attempts_for_task(self, task_id: str) -> list[Attempt]:
        """Return every attempt stored for a task."""
        return [a for a in self.attempts.values() if a.task_id == task_id]

    def save_reservation(self, reservation: Reservation) -> None:
        """Store the reservation under its attempt ID, replacing the old one."""
        self.reservations[reservation.attempt_id] = reservation

    def get_reservation(self, attempt_id: str) -> Reservation | None:
        """Return the stored reservation, or None."""
        return self.reservations.get(attempt_id)

    def save_wait_condition(self, condition: CiWaitCondition) -> None:
        """Store a wait condition under its task ID, replacing the old one."""
        self.wait_conditions[condition.task_id] = condition

    def get_wait_condition(self, task_id: str) -> CiWaitCondition | None:
        """Return the stored wait condition, or None."""
        return self.wait_conditions.get(task_id)

    def append_event(self, event: Event) -> None:
        """Append an event to the log."""
        self.events.append(event)

    def events_for_task(self, task_id: str) -> list[Event]:
        """Return every event stored for a task."""
        return [e for e in self.events if e.task_id == task_id]

    def ready_tasks(self, project_id: str) -> list[Task]:
        """Return the ready tasks for a project."""
        return [t for t in self.tasks.values() if t.project_id == project_id and t.status == "Ready"]
