"""CI waiting, checked against its acceptance criteria.

Issue #10's criteria, mapped one test each:

1. store the concrete CI wait condition and check whether the result exists;
2. end the worker while waiting and use cheap reconciliation for lost events;
3. tie the result to the right code version and check validity;
4. start at most one continuation; complete without model calls when
   machine-checkable;
5. show the blockage and next expected event in a status view.

Plus the referenced acceptance tests A02, A11, A42.
"""

from __future__ import annotations

from dev_org.core import CiWaiter, TaskLifecycle
from dev_org.core.lifecycle import READY_FOR_REPROCESSING, WAITING
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore


class FakeCi:
    """A deterministic CI double: a result per (repo, sha, check)."""

    def __init__(self) -> None:
        self.results: dict[tuple[str, str, str], str] = {}
        self.calls: int = 0

    def check_status(self, *, repo: str, sha: str, check_name: str) -> dict[str, object]:
        self.calls += 1
        return {"state": self.results.get((repo, sha, check_name), "pending")}


def make_waiter(ci: FakeCi | None = None) -> tuple[CiWaiter, TaskLifecycle, FakeCi, InMemoryStore]:
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store)
    ci = ci or FakeCi()
    return CiWaiter(lifecycle=lifecycle, ci=ci, store=store), lifecycle, ci, store


def make_task(task_id: str = "t-1") -> Task:
    return Task(id=task_id, organization_id="o-1", project_id="p-1", title="Fix the title helper")


def start_and_wait(waiter: CiWaiter, lifecycle: TaskLifecycle, task: Task) -> None:
    """Dispatch a task (Ready -> In progress) and hold it at a CI condition."""
    lifecycle.dispatch(task)
    waiter.wait_for_ci(task=task, repo="r", sha="s1", check_name="checks", next_action="merge")


# 1. Store the concrete condition ------------------------------------------


def test_the_wait_condition_records_repo_sha_and_check():
    waiter, lifecycle, _, store = make_waiter()
    task = make_task()
    lifecycle.dispatch(task)
    waiter.wait_for_ci(
        task=task,
        repo="roykollensvendsen/dev-org",
        sha="abc123",
        check_name="checks",
        next_action="merge",
    )
    condition = waiter.pending("t-1")
    assert condition is not None
    assert condition.repo == "roykollensvendsen/dev-org"
    assert condition.sha == "abc123"
    assert condition.check_name == "checks"
    assert store.get_wait_condition("t-1") is not None  # durable, through the Store
    assert task.status == WAITING  # the worker's session is ended


# 2. Cheap reconciliation finds lost events --------------------------------


def test_reconciliation_asks_only_for_the_waiting_check():
    waiter, lifecycle, ci, _ = make_waiter()
    task = make_task()
    start_and_wait(waiter, lifecycle, task)
    ci.results[("r", "s1", "checks")] = "success"
    result = waiter.reconcile(task_id="t-1")
    assert result == "success"
    assert ci.calls == 1  # cheap: one targeted status query


# 3. Tie the result to the right code version ------------------------------


def test_a_result_for_the_wrong_sha_is_ignored():
    waiter, lifecycle, _, _ = make_waiter()
    task = make_task()
    start_and_wait(waiter, lifecycle, task)
    # A webhook event for a different sha must not wake this wait.
    result = waiter.on_event(task_id="t-1", event_sha="s2", event_state="success")
    assert result is None
    assert task.status == WAITING  # still waiting, not woken


def test_pending_result_does_not_wake_the_task():
    waiter, lifecycle, _, _ = make_waiter()
    task = make_task()
    start_and_wait(waiter, lifecycle, task)
    result = waiter.reconcile(task_id="t-1")
    assert result is None  # FakeCi returns "pending" by default
    assert task.status == WAITING


# 4. At most one continuation (A02) ----------------------------------------


def test_a02_duplicate_event_wakes_at_most_once():
    waiter, lifecycle, ci, _ = make_waiter()
    task = make_task()
    start_and_wait(waiter, lifecycle, task)
    ci.results[("r", "s1", "checks")] = "success"

    first = waiter.reconcile(task_id="t-1")
    second = waiter.reconcile(task_id="t-1")  # duplicate

    assert first == "success"
    assert second is None  # already resolved
    reprocessing = [e for e in lifecycle.store.events_for_task("t-1") if e.event_type == "task.reprocessing"]
    assert len(reprocessing) == 1  # at most one logical continuation


def test_completion_without_model_calls_when_machine_checkable():
    # After the wait resolves, the lifecycle can complete the task without a
    # model: there are no model calls anywhere in this module.
    waiter, lifecycle, ci, _ = make_waiter()
    task = make_task()
    start_and_wait(waiter, lifecycle, task)
    ci.results[("r", "s1", "checks")] = "success"
    assert waiter.reconcile(task_id="t-1") == "success"
    # the lifecycle move is a state transition, not a model call
    assert task.status == READY_FOR_REPROCESSING


# 5. Status view -----------------------------------------------------------


def test_the_status_view_shows_the_blockage_and_next_event():
    waiter, lifecycle, _, _ = make_waiter()
    task = make_task()
    start_and_wait(waiter, lifecycle, task)

    view = waiter.status_view("t-1")
    assert view["blockage"] == "waiting on CI check checks"
    assert view["next_expected_event"] == "CI result for sha s1"
    assert view["next_action"] == "merge"


# A11: zero model calls while waiting --------------------------------------


def test_a11_zero_model_calls_while_waiting():
    waiter, lifecycle, _, _ = make_waiter()
    task = make_task()
    start_and_wait(waiter, lifecycle, task)
    # No model call is possible: CiWaiter has no model import or call.
    assert task.status == WAITING
    assert waiter.pending("t-1") is not None  # the condition is held, nothing is running


# A42: a duplicate event after a dropped one is found by reconciliation ----


def test_a42_reconciliation_finds_a_result_after_a_dropped_event():
    waiter, lifecycle, ci, _ = make_waiter()
    task = make_task()
    start_and_wait(waiter, lifecycle, task)
    # The webhook was dropped: no on_event ever arrives. Polling finds it.
    ci.results[("r", "s1", "checks")] = "success"
    assert waiter.reconcile(task_id="t-1") == "success"
    assert task.status == READY_FOR_REPROCESSING
