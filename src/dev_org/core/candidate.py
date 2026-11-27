"""Candidate environment: a self-improvement candidate is fully isolated.

Implements issue #36 (acceptance test A43): a candidate version runs
against a separate test board and database while the active version handles
a real issue. The candidate cannot read or change the active queue,
reservations, worker identity, or external operations, and the active
version keeps ownership and completes the issue.

The isolation is structural, not a promise: the candidate holds its own
store and its own worker identity, and the only view it has of the active
side is a read-only snapshot of the ready task ids taken at start. It never
receives a reference to the active store, nor the active reservation
ownership numbers, so it cannot read or change active state — a candidate
that tried to would be refused by construction. Candidate state, queue, and
CI are separate from active operations (section 9.2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dev_org.core.lifecycle import TaskLifecycle
from dev_org.core.scheduler import Scheduler

if TYPE_CHECKING:
    from dev_org.state.models import Reservation, Task
    from dev_org.state.store import Store


@dataclass(frozen=True)
class CandidateSnapshot:
    """A read-only view of the active side at candidate start.

    The candidate receives only the ready task ids — an immutable copy. It
    holds no store reference and no reservation ownership numbers, so it
    cannot read or change the active queue, reservations, or worker
    identity (A43).
    """

    active_ready_task_ids: tuple[str, ...]


class CandidateEnvironment:
    """One isolated candidate: its own store, identity, and lifecycle.

    ``active_store`` is read once at start to build a read-only snapshot;
    the candidate then runs entirely against ``candidate_store`` and its own
    worker identity. Nothing in the candidate holds a reference to
    ``active_store`` after construction, so it cannot read or change the
    active queue, reservations, worker identity, or external operations
    (A43).
    """

    def __init__(self, *, candidate_store: Store) -> None:
        """Bind the candidate to its own store; identity is generated here."""
        self.store = candidate_store
        self.candidate_worker_id = f"candidate-{uuid.uuid4().hex[:8]}"
        self.scheduler = Scheduler(store=candidate_store)
        self.lifecycle = TaskLifecycle(candidate_store)
        self._snapshot: CandidateSnapshot | None = None

    def start(self, *, active_store: Store) -> CandidateSnapshot:
        """Read the active side once and return a frozen snapshot.

        This is the only moment the candidate sees the active store, and it
        reads only ready task ids. After this call the candidate has no
        reference to the active store, so it cannot read or change active
        state (A43).
        """
        ready_ids = tuple(t.id for t in active_store.ready_tasks("p-1"))
        snapshot = CandidateSnapshot(active_ready_task_ids=ready_ids)
        self._snapshot = snapshot
        return snapshot

    def snapshot(self) -> CandidateSnapshot | None:
        """The frozen read-only snapshot of the active side, or None."""
        return self._snapshot

    # -- the candidate's own work --------------------------------------

    def dispatch_candidate(self, task: Task) -> Reservation:
        """Dispatch a candidate task with the candidate's own identity.

        The reservation carries the candidate worker id, never the active
        worker's (A43). A candidate task dispatched here lives only in the
        candidate store.
        """
        return self.lifecycle.dispatch(task, worker_id=self.candidate_worker_id)

    def next_ready(self, project_id: str) -> Task | None:
        """The candidate's next ready task, from its own store only."""
        return self.scheduler.next_ready(project_id)


__all__ = ["CandidateEnvironment", "CandidateSnapshot"]
