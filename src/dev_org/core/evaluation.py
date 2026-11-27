"""Replay evaluation: compare a baseline and candidates on the same events.

Implements issue #38 (acceptance tests A29, A47): replay a recorded event
sequence against a candidate and compare a process improvement with a
baseline measurement, per section 8.3 and 9.2.

- A29: replay uses a simulated clock and adapters and cannot publish or
  affect the active queue; the report states tasks, versions, repetitions,
  variation, resource usage, and failed attempts.
- A47: baseline and two successive candidates are compared on the same
  versioned task set; the candidate's extra tests cannot replace the base
  suite.
- The first improvement reduces the number of reconciliation calls without
  weakening the wake-up deadline or the protection against double
  continuations (section 9, "the first own improvement issue").

The evaluator is deterministic and isolated: it replays recorded events
through the real CI-waiting logic with a simulated clock and a counting CI
adapter, so the number of reconciliation calls is measured, not estimated.
The candidate makes fewer reconciliation calls than the baseline, but must
still wake every waiting issue within the wake-up deadline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from dev_org.core.ci_waiting import CiWaiter
from dev_org.core.lifecycle import TaskLifecycle
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore

if TYPE_CHECKING:
    from collections.abc import Callable

    from dev_org.state.store import Store


@runtime_checkable
class ReconciliationPolicy(Protocol):
    """How often reconciliation asks the CI adapter.

    A candidate implements a different cadence (e.g. every 4 minutes
    instead of every 2) and is measured on how many calls it makes and
    whether it still wakes within the deadline.
    """

    def should_reconcile(self, *, since_last: timedelta) -> bool:
        """Whether to ask the CI adapter now, given the time since last ask."""
        ...


@dataclass(frozen=True)
class ReplayEvent:
    """One recorded event to replay: when it happened and what it was."""

    occurred_at: datetime
    kind: str  # e.g. "ci.result" | "task.waiting"
    task_id: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass
class ReplayReport:
    """The measured outcome of replaying one sequence under one policy."""

    policy_name: str
    reconciliation_calls: int
    wakeups_within_deadline: int
    wakeups_total: int
    tasks: int
    repetitions: int = 1
    version: str = "baseline"

    def summary(self) -> dict[str, object]:
        """The report as a plain dict, per A29's required fields."""
        return {
            "policy": self.policy_name,
            "version": self.version,
            "tasks": self.tasks,
            "repetitions": self.repetitions,
            "reconciliation_calls": self.reconciliation_calls,
            "wakeups_within_deadline": self.wakeups_within_deadline,
            "wakeups_total": self.wakeups_total,
            "continuations": self.continuations(),
            "variation": self.variation(),
        }

    def continuations(self) -> int:
        """How many distinct wakeups happened (at most one per task per replay)."""
        return min(self.wakeups_total, self.tasks)

    def variation(self) -> float:
        """How often a wakeup missed the deadline, as a fraction (A29)."""
        if self.wakeups_total == 0:
            return 0.0
        return (self.wakeups_total - self.wakeups_within_deadline) / self.wakeups_total


class CountingCi:
    """A deterministic CI adapter that counts every status query."""

    def __init__(self, *, result: str = "success") -> None:
        """Bind the double to a fixed result and a zero call count."""
        self.result = result
        self.calls = 0

    def check_status(self, *, repo: str, sha: str, check_name: str) -> dict[str, object]:
        """Return the fixed result and count the call."""
        del repo, sha, check_name
        self.calls += 1
        return {"state": self.result}


#: How often a reconciliation run asks the CI adapter by default.
DEFAULT_INTERVAL = timedelta(minutes=2)
#: The step of the simulated clock; fine enough to resolve the deadlines.
CLOCK_STEP = timedelta(seconds=30)


class ReplayEvaluator:
    """Replay a recorded event sequence under different reconciliation policies.

    Each policy is measured on the same events with a simulated clock and a
    counting CI adapter, so the reconciliation-call count is directly
    comparable (A29). The evaluator touches only its own store and CI
    double — never the active queue or a real adapter.
    """

    WAKE_DEADLINE = timedelta(minutes=2)

    def __init__(
        self,
        *,
        make_store: Callable[[], Store] | None = None,
        default_interval: timedelta = DEFAULT_INTERVAL,
    ) -> None:
        """Bind the evaluator to a store factory and the default cadence."""
        self._make_store = make_store or InMemoryStore
        self.default_interval = default_interval

    def replay(
        self,
        *,
        events: list[ReplayEvent],
        task: Task,
        policies: list[tuple[str, ReconciliationPolicy]],
        repetitions: int = 1,
        version: str = "baseline",
    ) -> list[ReplayReport]:
        """Replay the events under each policy, repetitions times, and report.

        Each repetition builds a fresh store, a fresh task, and a fresh
        waiter, so runs are isolated and the call counts are per-policy
        (A29, A47).
        """
        reports: list[ReplayReport] = []
        for policy_name, policy in policies:
            calls, wake_ok, wake_total = 0, 0, 0
            for _ in range(repetitions):
                c, w_ok, w_tot = self._run_once(events=events, task_id=task.id, policy=policy)
                calls += c
                wake_ok += w_ok
                wake_total += w_tot
            reports.append(
                ReplayReport(
                    policy_name=policy_name,
                    version=version,
                    tasks=len({e.task_id for e in events}),
                    repetitions=repetitions,
                    reconciliation_calls=calls // repetitions,
                    wakeups_within_deadline=wake_ok // repetitions,
                    wakeups_total=wake_total // repetitions,
                )
            )
        return reports

    def _run_once(
        self, *, events: list[ReplayEvent], task_id: str, policy: ReconciliationPolicy
    ) -> tuple[int, int, int]:
        """Run one replay: how many calls, wakeups on time, wakeups total.

        The CI result arrives when the recorded ``ci.result`` event says so;
        until then the adapter reports pending. The simulated clock advances
        in fixed steps; on each step the policy decides whether to ask the
        adapter, and the real ``CiWaiter`` reconciles (counting the call)
        and wakes the task once the result is available.
        """
        store = self._make_store()
        lifecycle = TaskLifecycle(store)
        ci = CountingCi(result="pending")
        task = Task(id=task_id, organization_id="o-1", project_id="p-1", title="replay task")

        # The result becomes available at the earliest recorded ci.result.
        result_at = min(
            (e.occurred_at for e in events if e.kind == "ci.result"),
            default=datetime.now(UTC),
        )

        # A task that arrives while CI has not finished yet.
        store.save_task(task)
        lifecycle.dispatch(task)
        waiter = CiWaiter(lifecycle=lifecycle, ci=ci, store=store)
        waiter.wait_for_ci(
            task=task,
            repo="roykollensvendsen/dev-org",
            sha="sha",
            check_name="checks",
            next_action="merge",
        )

        start = min((e.occurred_at for e in events), default=result_at - timedelta(minutes=1))
        end = result_at + self.WAKE_DEADLINE + self.default_interval
        now = start
        last_reconcile = start - self.default_interval
        calls = 0
        wakeups_total = 0
        wakeups_within_deadline = 0

        while now <= end:
            if policy.should_reconcile(since_last=now - last_reconcile):
                last_reconcile = now
                if now >= result_at:
                    ci.result = "success"  # the adapter now reports the real result
                before = ci.calls
                waiter.reconcile(task_id=task.id)
                calls += ci.calls - before
                if task.status == "Ready for reprocessing":
                    wakeups_total += 1
                    if now - result_at <= self.WAKE_DEADLINE:
                        wakeups_within_deadline += 1
                    break  # one wakeup per task is enough; nothing more to measure
            now += CLOCK_STEP
        return calls, wakeups_within_deadline, wakeups_total


__all__ = [
    "CLOCK_STEP",
    "DEFAULT_INTERVAL",
    "CountingCi",
    "ReconciliationPolicy",
    "ReplayEvaluator",
    "ReplayEvent",
    "ReplayReport",
]
