"""The queue serves the client's highest-priority ready work first (pilot bug).

The specification's section 1 says dev-org must first do "the client's
highest-priority, clarified work", and acceptance test A03 requires priority
to carry all the way to the necessary resource. This test is the agreed
check for the #11 pilot bug: an earlier-created lower-priority task must not
be handed to a worker ahead of a higher-priority one that is already ready.

It was red before the fix (the queue returned tasks in insertion order, so
a P2 task created before a P0 was dispatched first) and is green after it.
"""

from datetime import UTC, datetime

from dev_org.core.lifecycle import TaskLifecycle
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore


def _clock() -> datetime:
    return datetime(2026, 11, 27, 9, 0, tzinfo=UTC)


def make_task(task_id: str, *, priority: str) -> Task:
    return Task(
        id=task_id,
        organization_id="o-1",
        project_id="p-1",
        title=f"{priority} work",
        priority=priority,  # type: ignore[arg-type]
    )


def test_next_ready_prefers_the_highest_priority_ready_task():
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store, _clock)

    # The lower-priority task is created first and is already ready.
    low = make_task("t-low", priority="P2")
    high = make_task("t-high", priority="P0")
    store.save_task(low)
    store.save_task(high)

    nxt = lifecycle.next_ready("p-1")
    assert nxt is not None
    assert nxt.id == "t-high", f"expected the P0 task, got {nxt.id} ({nxt.priority})"


def test_ready_tasks_are_sorted_most_urgent_first():
    store = InMemoryStore()
    for task_id, priority in (("t-p2", "P2"), ("t-p0", "P0"), ("t-p1", "P1"), ("t-p0b", "P0")):
        store.save_task(make_task(task_id, priority=priority))

    order = [t.id for t in store.ready_tasks("p-1")]
    # Highest priority first; within the same priority the earlier one stays first.
    assert order.index("t-p0") < order.index("t-p0b") < order.index("t-p1") < order.index("t-p2"), order


def test_in_progress_tasks_are_not_returned_as_ready():
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store, _clock)
    task = make_task("t-busy", priority="P0")
    store.save_task(task)
    lifecycle.dispatch(task)  # now in progress, not ready

    assert all(t.id != "t-busy" for t in store.ready_tasks("p-1"))
    assert lifecycle.next_ready("p-1") is None
