"""CI waiting: hold a task at a concrete CI wait condition and wake it once.

Implements issue #10 on top of the task lifecycle (section 5): a worker
ends its session while CI runs, a durable wait condition records what is
expected and for which code version, cheap reconciliation finds lost
events, and waking creates at most one continuation (A02). Completing
without model calls when every criterion is machine-checkable is the
lifecycle's job; this module supplies the CI-specific pieces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dev_org.core.lifecycle import TaskLifecycle
    from dev_org.state.models import Task


@runtime_checkable
class CiAdapter(Protocol):
    """The CI status contract (section 4): what a check run reports."""

    def check_status(self, *, repo: str, sha: str, check_name: str) -> dict[str, object]:
        """Return the current status of one check for a commit sha."""
        ...


@dataclass
class CiWaitCondition:
    """The durable record of one CI wait (section 5: Waiting)."""

    task_id: str
    repo: str
    sha: str  # the code version the result must belong to
    check_name: str
    next_action: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved: bool = False
    result: str | None = None  # "success" | "failure" | "pending"


class CiWaiter:
    """Hold tasks at a CI wait condition and reconcile them cheaply.

    ``store`` holds the wait conditions; ``lifecycle`` moves the task; the
    ``ci`` adapter reports check status. Reconciliation is cheap by design:
    it only asks the adapter for the specific check/sha it is waiting on.
    """

    def __init__(
        self,
        *,
        lifecycle: TaskLifecycle,
        ci: CiAdapter,
        store: CiWaitStore | None = None,
    ) -> None:
        """Bind the waiter to the lifecycle, a CI adapter, and a wait store."""
        self.lifecycle = lifecycle
        self.ci = ci
        self.store = store or CiWaitStore()

    def wait_for_ci(self, *, task: Task, repo: str, sha: str, check_name: str, next_action: str) -> None:
        """Record the concrete CI wait condition and put the task in Waiting.

        The wait condition carries the sha so a later result is only trusted
        when it belongs to the same code version.
        """
        self.store.save(
            CiWaitCondition(
                task_id=task.id,
                repo=repo,
                sha=sha,
                check_name=check_name,
                next_action=next_action,
            )
        )
        self.lifecycle.wait(task, wait_condition=f"ci:{repo}:{sha}:{check_name}", next_action=next_action)

    def reconcile(self, *, task: Task, repo: str, sha: str, check_name: str) -> str | None:
        """Ask the adapter for the current result and wake the task once.

        Returns the result ("success"/"failure") when the wait is resolved,
        or None while still pending. A duplicate event or a result for the
        wrong sha is ignored: at most one logical continuation (A02).
        """
        condition = self.store.get(task.id)
        if condition is None or condition.resolved:
            return None
        if condition.sha != sha:
            return None  # result belongs to a different code version

        status = self.ci.check_status(repo=repo, sha=sha, check_name=check_name)
        state = status.get("state")
        if state not in ("success", "failure"):
            return None  # still pending; reconcile again later

        condition.resolved = True
        condition.result = state
        self.store.save(condition)
        self.lifecycle.wake(task, event_key=f"ci:{sha}:{check_name}:{state}")
        return state

    def pending(self, task_id: str) -> CiWaitCondition | None:
        """The unresolved wait condition for a task, or None."""
        condition = self.store.get(task_id)
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


class CiWaitStore:
    """Durable (process-scoped) record of CI wait conditions by task."""

    def __init__(self) -> None:
        """Create an empty store."""
        self._by_task: dict[str, CiWaitCondition] = {}

    def save(self, condition: CiWaitCondition) -> None:
        """Store a wait condition under its task ID."""
        self._by_task[condition.task_id] = condition

    def get(self, task_id: str) -> CiWaitCondition | None:
        """Return the stored wait condition for a task, or None."""
        return self._by_task.get(task_id)
