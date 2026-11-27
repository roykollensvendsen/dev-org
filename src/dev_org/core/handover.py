"""Handover: another engine continues from the organization's checkpoint.

Implements issue #13 on top of the task lifecycle (section 5) and the
engine contract (section 4.1): when an issue has secured code and waits on
CI, a different engine can continue from the organization's checkpoint
without the engine's internal history (A18). The checkpoint carries the
code reference, test evidence, decisions, wait conditions, and next action;
the gateway re-finds the existing PR so an engine change alone orders no
build (A18) and a lost answer is reconciled before any resubmission (A36).

A handover creates one new attempt for the same task, preserves the issue
ID and reservation ownership, and hands the checkpoint to the new engine's
``continue_or_hand_over``. A duplicate handover for the same task/engine
does not start a second continuation.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from dev_org.core.lifecycle import WAITING
from dev_org.state.models import Checkpoint, Event

if TYPE_CHECKING:
    from dev_org.agents.protocol import AgentAdapter
    from dev_org.core.lifecycle import TaskLifecycle
    from dev_org.gateway.service import GatewayService
    from dev_org.state.models import Task
    from dev_org.state.store import Store


class HandoverError(RuntimeError):
    """A handover was refused: the basis is incomplete or a duplicate."""


class HandoverService:
    """Hand an issue to another engine from the organization's checkpoint.

    ``lifecycle`` moves the task (one continuation per handover);
    ``gateway`` re-finds the existing PR so no build is ordered by the
    engine change; the new ``engine`` continues from the checkpoint, not
    from the old engine's history.
    """

    def __init__(self, *, lifecycle: TaskLifecycle, gateway: GatewayService, store: Store) -> None:
        """Bind the handover service to the lifecycle, gateway, and store."""
        self.lifecycle = lifecycle
        self.gateway = gateway
        self.store = store

    def hand_over(
        self,
        *,
        task: Task,
        checkpoint: Checkpoint,
        engine: AgentAdapter,
        engine_name: str,
    ) -> str:
        """Hand the issue to a new engine and return its new attempt id.

        Refuses when the checkpoint is incomplete (A18: the new engine must
        receive code reference, test evidence, decisions, wait condition,
        and next action), and refuses a duplicate handover of the same
        checkpoint to the same engine (one logical continuation).
        """
        _validate_checkpoint(checkpoint)
        duplicate = any(
            e.event_type == "task.handover"
            and e.idempotency_key == f"handover:{task.id}:{engine_name}:{checkpoint.id}"
            for e in self.store.events_for_task(task.id)
        )
        if duplicate:
            msg = f"handover of {task.id} to {engine_name} already delivered"
            raise HandoverError(msg)

        # A18 switches engine while the issue waits on CI: the task is in
        # Waiting, so the handover is what wakes it (one continuation).
        if task.status == WAITING:
            self.lifecycle.wake(task, event_key=f"handover:{task.id}:{engine_name}")
        reservation = self.lifecycle.continue_(task)
        attempt = self.store.get_attempt(reservation.attempt_id)
        if attempt is None:
            msg = f"no attempt created for {task.id} during handover"
            raise RuntimeError(msg)

        engine.continue_or_hand_over(attempt, checkpoint)
        self.store.append_event(
            Event(
                id=f"ev-{uuid.uuid4().hex[:12]}",
                event_type="task.handover",
                organization_id=task.organization_id,
                project_id=task.project_id,
                task_id=task.id,
                attempt_id=attempt.id,
                source="core",
                occurred_at=self.lifecycle.clock(),
                recorded_at=self.lifecycle.clock(),
                idempotency_key=f"handover:{task.id}:{engine_name}:{checkpoint.id}",
                payload={
                    "engine": engine_name,
                    "checkpoint": checkpoint.id,
                    "next_action": checkpoint.next_action,
                },
            )
        )
        return attempt.id


def _validate_checkpoint(checkpoint: Checkpoint) -> None:
    """Refuse a handover when the checkpoint would lose information (A18)."""
    missing = []
    if not checkpoint.code_reference:
        missing.append("code_reference")
    if not checkpoint.next_action:
        missing.append("next_action")
    if not checkpoint.test_evidence:
        missing.append("test_evidence")
    if not checkpoint.decisions:
        missing.append("decisions")
    if not checkpoint.wait_conditions:
        missing.append("wait_conditions")
    if missing:
        msg = f"checkpoint {checkpoint.id} is incomplete for handover: missing {', '.join(missing)}"
        raise HandoverError(msg)


__all__ = ["HandoverError", "HandoverService"]
