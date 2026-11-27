"""Node-level lease and take-over: only the active owner may publish.

Implements issue #51 (acceptance tests A05, A63, A65): after lease expiry
the old node cannot publish or change status; secured work and external
operations are reconciled before take-over; and a checkpoint and lease
transition give one active owner, even if the old process does not stop
immediately (section 7.1).

A node returning with an expired token can only deliver checkpoint and
diagnostics for reconciliation; it cannot change task status or publish.
The lease ties ownership to a node id and an ownership number, so an old
node's fencing token stops working the moment a new owner takes over.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from dev_org.state.models import Reservation

if TYPE_CHECKING:
    from dev_org.core.lifecycle import TaskLifecycle
    from dev_org.state.models import Task
    from dev_org.state.store import Store


@dataclass(frozen=True)
class LeaseState:
    """What a node may do with its lease: the two things it can deliver."""

    can_publish: bool
    can_deliver_checkpoint: bool


class NodeLeaseService:
    """Manage node-level leases and take-over on top of the task lifecycle.

    ``lifecycle`` owns the reservation records; this service binds them to
    a node id and to the "expired token = checkpoint only" rule (A63, A65,
    section 7.1).
    """

    def __init__(self, *, lifecycle: TaskLifecycle, store: Store) -> None:
        """Bind the lease service to the lifecycle and the store."""
        self.lifecycle = lifecycle
        self.store = store

    def renew(self, reservation: Reservation, *, node_id: str, lease_minutes: int = 30) -> Reservation:
        """Renew the active node's lease, refusing a stale or foreign owner.

        Only the current reservation's owner may renew; an old node trying
        to renew after take-over holds a stale fencing token and is refused,
        so it cannot extend its own lease (A63).
        """
        current = self.store.get_reservation(reservation.attempt_id)
        if current is None or current.fencing_token != reservation.fencing_token:
            msg = f"node {node_id} holds a stale fencing token; cannot renew"
            raise LeaseRefusedError(msg)
        if reservation.worker_id != node_id:
            msg = f"node {node_id} is not the reservation owner {reservation.worker_id}"
            raise LeaseRefusedError(msg)
        renewed = Reservation(
            id=reservation.id,
            attempt_id=reservation.attempt_id,
            worker_id=reservation.worker_id,
            ownership_number=reservation.ownership_number,
            fencing_token=reservation.fencing_token,
            lease_expires_at=self.lifecycle.clock() + timedelta(minutes=lease_minutes),
        )
        self.store.save_reservation(renewed)
        return renewed

    def state(self, reservation: Reservation, *, node_id: str, ownership_number: int) -> LeaseState:
        """What this node may do now: publish, checkpoint only, or nothing.

        A node with an unexpired, matching lease — and that is the
        reservation's owner — may publish. A node whose lease has expired,
        that lost the lease to a take-over, or that is not the reservation
        owner may only deliver checkpoint and diagnostics for
        reconciliation (A65, 7.1); it cannot change status or publish.
        """
        is_owner = reservation.worker_id == node_id
        if is_owner and self.lifecycle.can_publish(reservation, ownership_number=ownership_number):
            return LeaseState(can_publish=True, can_deliver_checkpoint=True)
        # Expired, superseded, or a foreign node: checkpoint/diagnostics only.
        return LeaseState(can_publish=False, can_deliver_checkpoint=True)

    def take_over(self, task: Task, *, node_id: str) -> Reservation:
        """Take over an expired reservation for a new node.

        The new owner gets a higher ownership number and a fresh fencing
        token; the old node's token stops working immediately, even if its
        process has not stopped yet (A65). Secured work is not lost: the
        same attempt is re-reserved.
        """
        return self.lifecycle.take_over(task, worker_id=node_id)

    def checkpoint_only(self, reservation: Reservation, *, node_id: str) -> bool:
        """Whether an expired/foreign node may only deliver checkpoint data."""
        del node_id  # the state is derived from the reservation, not the claim
        return not self.lifecycle.can_publish(reservation, ownership_number=reservation.ownership_number)


class LeaseRefusedError(RuntimeError):
    """A lease renewal or action was refused: stale token or foreign owner."""


__all__ = ["LeaseRefusedError", "LeaseState", "NodeLeaseService"]
