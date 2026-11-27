"""Node-level lease and take-over, checked against its acceptance criteria.

Issue #51's criteria, mapped one test each, per A05, A63, and A65:

1. after lease expiry the old node cannot publish or change status; a new
   node takes over without losing secured work (A05, A63);
2. only the active lease owner can publish (A05, repeated on two nodes);
3. checkpoint and lease transition give one active owner; the old process
   cannot publish even if it does not stop immediately (A65);
4. a node returning with an expired token can only deliver
   checkpoint/diagnostics, not change status or publish (section 7.1).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dev_org.core import NodeLeaseService, TaskLifecycle
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore


class FakeClock:
    """A clock a test can advance without sleeping."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 28, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: int) -> None:
        self.now += timedelta(minutes=minutes)


def make_rig() -> tuple[NodeLeaseService, TaskLifecycle, InMemoryStore, FakeClock, Task]:
    store = InMemoryStore()
    clock = FakeClock()
    lifecycle = TaskLifecycle(store, clock)
    task = Task(id="t-1", organization_id="o-1", project_id="p-1", title="Fix the title helper")
    store.save_task(task)
    lease = NodeLeaseService(lifecycle=lifecycle, store=store)
    return lease, lifecycle, store, clock, task


# 1. Expired lease: old node cannot publish; take-over keeps the work (A05/A63)


def test_an_expired_lease_blocks_the_old_node_from_publishing():
    lease, lifecycle, _, clock, task = make_rig()
    old = lifecycle.dispatch(task, worker_id="node-a")

    clock.advance(minutes=45)  # lease was 30 minutes; it has expired
    state = lease.state(old, node_id="node-a", ownership_number=old.ownership_number)
    assert state.can_publish is False  # the old node cannot publish (A63)
    assert state.can_deliver_checkpoint is True  # checkpoint only (7.1)


def test_take_over_gives_the_new_node_ownership_without_losing_work():
    lease, lifecycle, store, clock, task = make_rig()
    old = lifecycle.dispatch(task, worker_id="node-a")

    clock.advance(minutes=45)
    new = lease.take_over(task, node_id="node-b")

    assert new.ownership_number > old.ownership_number  # higher number
    assert new.fencing_token != old.fencing_token  # fresh token
    # The old node can no longer publish, even with its own number (A65).
    old_state = lease.state(old, node_id="node-a", ownership_number=old.ownership_number)
    assert old_state.can_publish is False
    # The new owner publishes; the same attempt is re-reserved, no work lost.
    new_state = lease.state(new, node_id="node-b", ownership_number=new.ownership_number)
    assert new_state.can_publish is True
    assert store.get_attempt(new.attempt_id) is not None


# 2. Only the active owner publishes (A05) --------------------------------


def test_only_the_active_lease_owner_can_publish():
    lease, lifecycle, _, _, task = make_rig()
    owner = lifecycle.dispatch(task, worker_id="node-a")

    state = lease.state(owner, node_id="node-a", ownership_number=owner.ownership_number)
    assert state.can_publish is True

    # A different node claiming the same reservation is not the owner.
    foreign = lease.state(owner, node_id="node-b", ownership_number=owner.ownership_number)
    assert foreign.can_publish is False


def test_a_stale_node_cannot_renew_after_take_over():
    lease, lifecycle, _, clock, task = make_rig()
    old = lifecycle.dispatch(task, worker_id="node-a")
    clock.advance(minutes=45)
    lease.take_over(task, node_id="node-b")

    # The old node tries to renew with its stale token: refused (A63).
    with pytest.raises(Exception, match="stale fencing token"):
        lease.renew(old, node_id="node-a")


# 3. One active owner even if the old process does not stop (A65) ---------


def test_the_old_process_cannot_publish_even_if_it_has_not_stopped():
    lease, lifecycle, _, clock, task = make_rig()
    old = lifecycle.dispatch(task, worker_id="node-a")
    clock.advance(minutes=45)
    lease.take_over(task, node_id="node-b")

    # The old process is still "running" (it did not stop immediately), but
    # its fencing token is superseded: it cannot publish (A65).
    assert lifecycle.can_publish(old, ownership_number=old.ownership_number) is False
    # And its state is checkpoint-only.
    state = lease.state(old, node_id="node-a", ownership_number=old.ownership_number)
    assert state.can_publish is False
    assert state.can_deliver_checkpoint is True


# 4. Expired token: checkpoint/diagnostics only (section 7.1) -------------


def test_an_expired_token_node_can_only_deliver_checkpoint_data():
    lease, lifecycle, _, clock, task = make_rig()
    reservation = lifecycle.dispatch(task, worker_id="node-a")
    clock.advance(minutes=45)  # token expired

    # The returning node may deliver checkpoint/diagnostics, but cannot
    # change status or publish (7.1).
    assert lease.checkpoint_only(reservation, node_id="node-a") is True
    assert (
        lease.state(reservation, node_id="node-a", ownership_number=reservation.ownership_number).can_publish
        is False
    )


def test_an_active_token_can_publish_and_is_not_checkpoint_only():
    lease, lifecycle, _, _, task = make_rig()
    reservation = lifecycle.dispatch(task, worker_id="node-a")
    assert lease.checkpoint_only(reservation, node_id="node-a") is False
    assert (
        lease.state(reservation, node_id="node-a", ownership_number=reservation.ownership_number).can_publish
        is True
    )
