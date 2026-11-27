"""CI waiting: hold a task at a concrete CI wait condition and wake it once.

Implements issue #10 on top of the task lifecycle (section 5): a worker
ends its session while CI runs, a durable wait condition records what is
expected and for which code version, cheap reconciliation finds lost
events, and waking creates at most one continuation (A02). Completing
without model calls when every criterion is machine-checkable is the
lifecycle's job; this module supplies the CI-specific pieces.

The wait condition is durable state (section 10.1) and lives in the Store
port, so a later PostgreSQL adapter persists it like everything else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from dev_org.state.models import CiWaitCondition

if TYPE_CHECKING:
    from dev_org.core.lifecycle import TaskLifecycle
    from dev_org.state.models import Task
    from dev_org.state.store import Store


@runtime_checkable
class CiAdapter(Protocol):
    """The CI status contract (section 4): what a check run reports."""

    def check_status(self, *, repo: str, sha: str, check_name: str) -> dict[str, object]:
        """Return the current status of one check for a commit sha."""
        ...


class CiWaiter:
    """Hold tasks at a CI wait condition and reconcile them cheaply.

    ``store`` holds the wait conditions (durable state); ``lifecycle`` moves
    the task; the ``ci`` adapter reports check status. Reconciliation is
    cheap by design: it asks the adapter only about the waiting check/sha,
    read from the stored condition.
    """

    def __init__(
        self,
        *,
        lifecycle: TaskLifecycle,
        ci: CiAdapter,
        store: Store,
    ) -> None:
        """Bind the waiter to the lifecycle, a CI adapter, and the durable store."""
        self.lifecycle = lifecycle
        self.ci = ci
        self.store = store

    def wait_for_ci(self, *, task: Task, repo: str, sha: str, check_name: str, next_action: str) -> None:
        """Record the concrete CI wait condition and put the task in Waiting.

        The wait condition carries the sha so a later result is only trusted
        when it belongs to the same code version.
        """
        self.store.save_wait_condition(
            CiWaitCondition(
                id=f"wait-{task.id}",
                task_id=task.id,
                repo=repo,
                sha=sha,
                check_name=check_name,
                next_action=next_action,
            )
        )
        self.lifecycle.wait(task, wait_condition=f"ci:{repo}:{sha}:{check_name}", next_action=next_action)

    def reconcile(self, *, task_id: str) -> str | None:
        """Poll the adapter for the stored condition's check and wake once.

        The sha and check are read from the stored condition, not from the
        caller: polling always concerns the commit we are waiting on. Returns
        the result when resolved, or None while still pending.
        """
        condition = self.store.get_wait_condition(task_id)
        if condition is None or condition.resolved:
            return None

        status = self.ci.check_status(
            repo=condition.repo,
            sha=condition.sha,
            check_name=condition.check_name,
        )
        state = status.get("state")
        if state not in ("success", "failure"):
            return None  # still pending; reconcile again later

        condition.resolved = True
        condition.result = state
        self.store.save_wait_condition(condition)
        task = self.store.get_task(task_id)
        if task is not None:
            self.lifecycle.wake(task, event_key=f"ci:{condition.sha}:{condition.check_name}:{state}")
        return state

    def on_event(self, *, task_id: str, event_sha: str, event_state: str) -> str | None:
        """Handle an incoming CI event with its own sha and result.

        A webhook carries the commit it ran on; the event is only trusted when
        its sha matches the stored condition's sha. A result for a different
        code version must not wake this wait.
        """
        condition = self.store.get_wait_condition(task_id)
        if condition is None or condition.resolved:
            return None
        if condition.sha != event_sha:
            return None  # result belongs to a different code version

        if event_state not in ("success", "failure"):
            return None
        condition.resolved = True
        condition.result = event_state
        self.store.save_wait_condition(condition)
        task = self.store.get_task(task_id)
        if task is not None:
            self.lifecycle.wake(task, event_key=f"ci:{condition.sha}:{condition.check_name}:{event_state}")
        return event_state

    def pending(self, task_id: str) -> CiWaitCondition | None:
        """The unresolved wait condition for a task, or None."""
        condition = self.store.get_wait_condition(task_id)
        return None if condition is None or condition.resolved else condition

    def status_view(self, task_id: str) -> dict[str, str]:
        """A simple status view: the blockage and the next expected event."""
        condition = self.pending(task_id)
        if condition is None:
            return {"blockage": "none", "next_expected_event": "none"}
        return {
            "blockage": f"waiting on CI check {condition.check_name}",
            "next_expected_event": f"CI result for sha {condition.sha}",
            "next_action": condition.next_action,
        }
