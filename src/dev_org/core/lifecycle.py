"""Task lifecycle: the authoritative state machine for one issue.

This is the core of issue #5, following the operational states in section 5
of the specification: Ready, In progress, Waiting, Ready for reprocessing,
Completed, Paused or ended. A task has a stable ID; an execution attempt is
one run; a reservation gives time-limited ownership with an ownership
number and a fencing token.

The lifecycle is deterministic and takes a ``Store`` and a clock, so the
tests can run it against the in-memory store with a simulated clock and a
simulated worker. Publishing and model calls are simulated here; the real
gateway and model access are later issues.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from dev_org.state.models import Attempt, Event, Reservation, Task

if TYPE_CHECKING:
    from dev_org.state.store import Store

#: Operational states from section 5.
READY = "Ready"
IN_PROGRESS = "In progress"
WAITING = "Waiting"
READY_FOR_REPROCESSING = "Ready for reprocessing"
COMPLETED = "Completed"
PAUSED_OR_ENDED = "Paused or ended"

#: Attempt statuses.
RUNNING = "running"
WAITING_ATTEMPT = "waiting"
COMPLETED_ATTEMPT = "completed"

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class TaskLifecycle:
    """Drive one task through its operational states.

    ``clock`` is injectable so a test can advance time without sleeping; the
    default is the real UTC clock. ``now`` is read once per public call so a
    test controls the moment each transition happens.
    """

    def __init__(self, store: Store, clock: Clock = _utc_now) -> None:
        """Bind the lifecycle to a store and a clock; the clock is injectable."""
        self.store = store
        self.clock = clock
        self._ownership = itertools.count(1)

    # -- transitions ---------------------------------------------------

    def dispatch(self, task: Task) -> Reservation:
        """Move a ready task to in progress and reserve it for a worker."""
        if task.status != READY:
            msg = f"cannot dispatch a task in state {task.status}"
            raise ValueError(msg)
        attempt = Attempt(id=_new_id("attempt"), task_id=task.id)
        reservation = Reservation(
            id=_new_id("reservation"),
            attempt_id=attempt.id,
            worker_id="worker-1",
            ownership_number=next(self._ownership),
            fencing_token=_new_id("token"),
            lease_expires_at=self.clock() + timedelta(minutes=30),
        )
        task.status = IN_PROGRESS
        self.store.save_task(task)
        self.store.save_attempt(attempt)
        self.store.save_reservation(reservation)
        self.store.append_event(
            Event(
                id=_new_id("event"),
                event_type="task.dispatched",
                organization_id=task.organization_id,
                project_id=task.project_id,
                task_id=task.id,
                attempt_id=attempt.id,
                source="core",
                occurred_at=self.clock(),
                recorded_at=self.clock(),
            )
        )
        return reservation

    def wait(self, task: Task, *, wait_condition: str, next_action: str) -> None:
        """Move an in-progress task to waiting, preserving the next action."""
        if task.status != IN_PROGRESS:
            msg = f"cannot wait from state {task.status}"
            raise ValueError(msg)
        task.status = WAITING
        self.store.save_task(task)
        self.store.append_event(
            Event(
                id=_new_id("event"),
                event_type="task.waiting",
                organization_id=task.organization_id,
                project_id=task.project_id,
                task_id=task.id,
                source="core",
                occurred_at=self.clock(),
                recorded_at=self.clock(),
                payload={"wait_condition": wait_condition, "next_action": next_action},
            )
        )

    def wake(self, task: Task, *, event_key: str) -> None:
        """Wake a waiting task, creating at most one continuation per event.

        A repeated ``event_key`` must not create a second logical
        continuation: the event log records what was already processed, and
        the task moves to ready-for-reprocessing only once per key.
        """
        if task.status != WAITING:
            return  # not waiting: nothing to wake
        already = any(
            e.event_type == "task.reprocessing" and e.idempotency_key == event_key
            for e in self.store.events_for_task(task.id)
        )
        if already:
            return
        task.status = READY_FOR_REPROCESSING
        self.store.save_task(task)
        self.store.append_event(
            Event(
                id=_new_id("event"),
                event_type="task.reprocessing",
                organization_id=task.organization_id,
                project_id=task.project_id,
                task_id=task.id,
                source="core",
                occurred_at=self.clock(),
                recorded_at=self.clock(),
                idempotency_key=event_key,
            )
        )

    def continue_(self, task: Task) -> Reservation:
        """Create one continuation from ready-for-reprocessing to in progress."""
        if task.status != READY_FOR_REPROCESSING:
            msg = f"cannot continue from state {task.status}"
            raise ValueError(msg)
        attempt = Attempt(id=_new_id("attempt"), task_id=task.id)
        reservation = Reservation(
            id=_new_id("reservation"),
            attempt_id=attempt.id,
            worker_id="worker-1",
            ownership_number=next(self._ownership),
            fencing_token=_new_id("token"),
            lease_expires_at=self.clock() + timedelta(minutes=30),
        )
        task.status = IN_PROGRESS
        self.store.save_task(task)
        self.store.save_attempt(attempt)
        self.store.save_reservation(reservation)
        return reservation

    def complete(self, task: Task) -> None:
        """Mark a task completed once its agreed criteria are met."""
        task.status = COMPLETED
        self.store.save_task(task)
        self.store.append_event(
            Event(
                id=_new_id("event"),
                event_type="task.completed",
                organization_id=task.organization_id,
                project_id=task.project_id,
                task_id=task.id,
                source="core",
                occurred_at=self.clock(),
                recorded_at=self.clock(),
            )
        )

    # -- ownership and publishing --------------------------------------

    def can_publish(self, reservation: Reservation, *, ownership_number: int) -> bool:
        """Only the active, unexpired owner may publish (section 5, A05).

        A stale owner has an expired lease or a lower ownership number, and
        is rejected. An expired reservation can be taken over: a new dispatch
        issues a higher ownership number and a new fencing token.
        """
        current = self.store.get_reservation(reservation.attempt_id)
        if current is None or current.fencing_token != reservation.fencing_token:
            return False
        if self.clock() >= current.lease_expires_at:
            return False
        return ownership_number == current.ownership_number

    def take_over(self, task: Task) -> Reservation:
        """Re-dispatch after an expired lease: new owner, higher number."""
        if task.status != IN_PROGRESS:
            msg = f"cannot take over a task in state {task.status}"
            raise ValueError(msg)
        attempt = self.store.attempts_for_task(task.id)[-1]
        reservation = Reservation(
            id=_new_id("reservation"),
            attempt_id=attempt.id,
            worker_id="worker-1",
            ownership_number=next(self._ownership),
            fencing_token=_new_id("token"),
            lease_expires_at=self.clock() + timedelta(minutes=30),
        )
        self.store.save_reservation(reservation)
        return reservation

    # -- queue ---------------------------------------------------------

    def next_ready(self, project_id: str) -> Task | None:
        """The next ready task, or None. An empty queue calls no models."""
        ready = self.store.ready_tasks(project_id)
        return ready[0] if ready else None
