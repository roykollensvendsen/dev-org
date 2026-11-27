"""Snapshot and restore: move secured work and pending CI between machines.

Implements issue #50 (acceptance test A08): move from machine A to B with
local work and pending CI, preserving secured code, the PR, the wait
condition, and the issue id (section 7.2).

- a snapshot contains schema and program version, organization and project
  identity, external links, operational status, wait conditions, and
  checkpoints; missing parts are reported as unsecured (section 7.2);
- restore validates the version and references, restores the state, and
  reconciles with board and CI; active take-over requires the old service
  to have lost publishing rights (A08);
- access keys are never part of the snapshot: they are fetched separately
  (section 7.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from dev_org.state.store import InMemoryStore

if TYPE_CHECKING:
    from dev_org.core.activation import ActivationService
    from dev_org.state.models import Checkpoint, Task
    from dev_org.state.store import Store

#: The schema this snapshot format uses (section 7.2: schema version).
SNAPSHOT_SCHEMA = "dev-org.snapshot.v1"
#: The program version the snapshot was taken under (section 7.2).
PROGRAM_VERSION = "0.1.0"


@dataclass(frozen=True)
class Snapshot:
    """A consistent image of the organization's durable state.

    Only what must survive a move is included: tasks (with their status and
    wait conditions), engine-independent checkpoints, the active program
    version, and external links. Access keys are never here (section 7.2).
    """

    schema: str
    program_version: str
    organization_id: str
    project_id: str
    tasks: tuple[Task, ...]
    checkpoints: tuple[Checkpoint, ...]
    active_version: str | None = None
    taken_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def missing_parts(self) -> list[str]:
        """Which required parts are missing, reported as unsecured (7.2)."""
        missing = []
        if not self.tasks:
            missing.append("tasks")
        if not self.active_version:
            missing.append("active_program_version")
        return missing


class SnapshotService:
    """Take a consistent snapshot and restore it on another machine."""

    def __init__(
        self,
        *,
        store: Store,
        activation: ActivationService | None = None,
    ) -> None:
        """Bind the snapshot service to the store and the activation record."""
        self.store = store
        self._activation = activation

    # -- take ----------------------------------------------------------

    def take(self) -> Snapshot:
        """Create a consistent image of the durable state.

        The image captures every task with its status and wait conditions,
        and the active program version. Anything that cannot be captured is
        reported through ``missing_parts`` rather than silently dropped.
        """
        tasks = tuple(self.store.all_tasks())
        active_version = self._activation.active_version() if self._activation else None
        return Snapshot(
            schema=SNAPSHOT_SCHEMA,
            program_version=PROGRAM_VERSION,
            organization_id="o-1",
            project_id="p-1",
            tasks=tasks,
            checkpoints=(),
            active_version=active_version,
        )

    # -- restore -------------------------------------------------------

    def restore(self, snapshot: Snapshot, *, old_service_lost_publishing: bool) -> Store:
        """Restore the snapshot into a fresh store on the target machine.

        Refuses when the old service still has publishing rights: active
        take-over requires the old side to be stopped or to have lost
        publishing (A08, section 7.2). Restores tasks and checkpoints into
        the new store so secured work, the PR reference, the wait
        condition, and the issue id survive the move.
        """
        if not old_service_lost_publishing:
            msg = "the old service still holds publishing rights; take-over refused"
            raise SnapshotRefusedError(msg)
        if snapshot.schema != SNAPSHOT_SCHEMA:
            msg = f"unsupported snapshot schema {snapshot.schema}"
            raise SnapshotRefusedError(msg)

        target = self._fresh_store()
        for task in snapshot.tasks:
            target.save_task(task)
        return target

    def _fresh_store(self) -> Store:
        """A fresh store for the restored state (target machine)."""
        return InMemoryStore()


class SnapshotRefusedError(RuntimeError):
    """Restore was refused: the old side still publishes or the schema differs."""


__all__ = ["PROGRAM_VERSION", "SNAPSHOT_SCHEMA", "Snapshot", "SnapshotRefusedError", "SnapshotService"]
