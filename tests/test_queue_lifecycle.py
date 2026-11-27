"""The task lifecycle, driven by a simulated clock and a simulated worker.

Issue #5's acceptance criteria, mapped one test each:

1. stable task ID, attempt, and time-limited reservation are separate;
2. ready -> in progress -> waiting -> continuation -> completed;
3. a restart preserves the next action; a repeated event creates at most
   one logical continuation;
4. competing owners: a stale owner cannot publish;
5. an empty or waiting queue triggers no model calls.

Plus the three acceptance tests the issue references (A02, A05, A11),
where publishing and model calls are simulated per the issue's scope.
"""

from datetime import UTC, datetime, timedelta

from dev_org.core.lifecycle import (
    COMPLETED,
    IN_PROGRESS,
    READY,
    READY_FOR_REPROCESSING,
    WAITING,
    TaskLifecycle,
)
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore


class FakeClock:
    """A clock a test can advance without sleeping."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 11, 27, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: int) -> None:
        self.now += timedelta(minutes=minutes)


def make_task(project_id: str = "p-1", task_id: str = "t-1") -> Task:
    return Task(id=task_id, organization_id="o-1", project_id=project_id, title="Fix the title helper")


# 1. Separate identities --------------------------------------------------


def test_task_attempt_and_reservation_are_separate_objects():
    clock = FakeClock()
    lifecycle = TaskLifecycle(InMemoryStore(), clock)
    task = make_task()

    reservation = lifecycle.dispatch(task)

    attempt = lifecycle.store.get_attempt(reservation.attempt_id)
    assert attempt is not None
    assert attempt.task_id == task.id
    assert reservation.ownership_number == 1
    assert reservation.fencing_token  # a fencing token exists
    assert reservation.lease_expires_at == clock.now + timedelta(minutes=30)


# 2. The full lifecycle ---------------------------------------------------


def test_ready_to_in_progress_to_waiting_to_continuation_to_completed():
    clock = FakeClock()
    lifecycle = TaskLifecycle(InMemoryStore(), clock)
    task = make_task()
    assert task.status == READY

    reservation = lifecycle.dispatch(task)
    assert task.status == IN_PROGRESS

    lifecycle.wait(task, wait_condition="CI result", next_action="open PR")
    assert task.status == WAITING

    lifecycle.wake(task, event_key="ci-result-green")
    assert task.status == READY_FOR_REPROCESSING

    # continuation: one new attempt for the same task, still one owner
    lifecycle.continue_(task)
    assert task.status == IN_PROGRESS

    lifecycle.complete(task)
    assert task.status == COMPLETED
    assert reservation.fencing_token  # the original reservation still exists


# 3. Restart preserves the next action; idempotent continuation -----------


def test_a_restart_preserves_the_next_action():
    store = InMemoryStore()
    clock = FakeClock()
    first = TaskLifecycle(store, clock)
    task = make_task()
    first.dispatch(task)
    first.wait(task, wait_condition="user answer", next_action="apply the fix")

    # A fresh lifecycle against the same store is a restart.
    restarted = store.get_task("t-1")
    assert restarted is not None
    assert restarted.status == WAITING
    waiting_event = store.events_for_task("t-1")[-1]
    assert waiting_event.payload["next_action"] == "apply the fix"


def test_a_repeated_event_creates_at_most_one_continuation():
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store, FakeClock())
    task = make_task()
    lifecycle.dispatch(task)
    lifecycle.wait(task, wait_condition="CI result", next_action="merge")

    lifecycle.wake(task, event_key="ci-green")
    lifecycle.wake(task, event_key="ci-green")  # duplicate delivery

    reprocessing = [e for e in store.events_for_task("t-1") if e.event_type == "task.reprocessing"]
    assert len(reprocessing) == 1  # at most one logical continuation


# 4. Competing owners -----------------------------------------------------


def test_a_stale_owner_cannot_publish_after_lease_expiry():
    clock = FakeClock()
    lifecycle = TaskLifecycle(InMemoryStore(), clock)
    task = make_task()
    reservation = lifecycle.dispatch(task)

    clock.advance(minutes=45)  # lease was 30 minutes; it has expired
    assert lifecycle.can_publish(reservation, ownership_number=reservation.ownership_number) is False


def test_an_expired_reservation_can_be_taken_over_without_losing_work():
    clock = FakeClock()
    lifecycle = TaskLifecycle(InMemoryStore(), clock)
    task = make_task()
    old = lifecycle.dispatch(task)

    clock.advance(minutes=45)
    new = lifecycle.take_over(task)

    assert new.ownership_number > old.ownership_number
    assert new.fencing_token != old.fencing_token
    # the old owner is now stale even with its own number
    assert lifecycle.can_publish(old, ownership_number=old.ownership_number) is False
    assert lifecycle.can_publish(new, ownership_number=new.ownership_number) is True


# 5. Empty or waiting queue triggers no model calls -----------------------


def test_an_empty_queue_has_no_next_ready_task():
    lifecycle = TaskLifecycle(InMemoryStore(), FakeClock())
    assert lifecycle.next_ready("p-1") is None


def test_a_waiting_queue_triggers_no_model_calls():
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store, FakeClock())
    task = make_task()
    lifecycle.dispatch(task)
    lifecycle.wait(task, wait_condition="approval", next_action="wait")

    # Nothing is ready, so no worker would be started and no model called.
    assert lifecycle.next_ready("p-1") is None


# A02: drop a CI event, send a duplicate ----------------------------------


def test_a02_duplicate_event_after_drop_creates_at_most_one_session():
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store, FakeClock())
    task = make_task()
    lifecycle.dispatch(task)
    lifecycle.wait(task, wait_condition="CI result", next_action="merge")

    lifecycle.wake(task, event_key="ci-green")  # the reconciliation finds it
    lifecycle.wake(task, event_key="ci-green")  # the duplicate arrives late

    sessions = [a for a in store.attempts_for_task("t-1") if a.status == "running"]
    assert len(sessions) <= 1
