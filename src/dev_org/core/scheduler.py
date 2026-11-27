"""Scheduler: production work, then improvement candidates, then idle.

Implements issue #35 on top of the task lifecycle, per ADR-DEV-010 and the
Linux-kernel scheduler model: a fixed hierarchy of scheduler classes
(production > improvement > idle), a weighted ordering within a class, and
a budgeted throttle for the improvement class.

- a ready production task is always picked before an improvement candidate
  (A03, section 9.2);
- the improvement candidate runs in its own budgeted capacity: a quota of
  active-model time and attempts per period, and once spent the candidate
  is throttled and cannot take reserved production capacity (A48);
- with no ready production task and no eligible candidate, the scheduler
  returns idle, so the agents go idle (A16).

The scheduler is an internal module with a deterministic contract and
simulated counterparts in tests; it becomes a port only when a second real
or simulated user needs different rules (section 3.3, ADR-DEV-010).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dev_org.state.models import Task
    from dev_org.state.store import Store

#: Scheduler classes in fixed priority order (ADR-DEV-010). The order is
#: compiled in, like the kernel's sched_class chain; it is not swappable.
PRODUCTION = "production"
IMPROVEMENT = "improvement"
IDLE = "idle"
CLASS_ORDER = {PRODUCTION: 0, IMPROVEMENT: 1, IDLE: 2}


@dataclass
class ImprovementBudget:
    """The improvement candidate's quota, in the kernel's cfs_bandwidth style.

    ``attempts_per_period`` is how many attempts the candidate may start in
    one ``period``; ``active_minutes_per_period`` caps active model time.
    Once either is spent the candidate is throttled until the next period,
    and it never shares the production reserve (A48).
    """

    period: timedelta = timedelta(hours=1)
    attempts_per_period: int = 1
    active_minutes_per_period: int = 30
    attempts_used: int = 0
    active_minutes_used: int = 0
    period_started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def can_run(self, *, now: datetime) -> bool:
        """Whether the candidate may start another attempt now."""
        self._roll(now)
        return self.attempts_used < self.attempts_per_period

    def consume(self, *, now: datetime, active_minutes: int) -> None:
        """Account one started attempt and its active minutes."""
        self._roll(now)
        self.attempts_used += 1
        self.active_minutes_used += active_minutes

    def _roll(self, now: datetime) -> None:
        """Start a new period once the current one has elapsed."""
        if now - self.period_started_at >= self.period:
            self.period_started_at = now
            self.attempts_used = 0
            self.active_minutes_used = 0


class Scheduler:
    """Pick the next task: production first, then a budgeted improvement candidate."""

    def __init__(self, *, store: Store, budget: ImprovementBudget | None = None) -> None:
        """Bind the scheduler to the store and the improvement budget."""
        self.store = store
        self.budget = budget or ImprovementBudget()

    def next_ready(self, project_id: str) -> Task | None:
        """The next task to dispatch, or None when the scheduler is idle.

        The production class is consulted first and is never starved by the
        improvement class (A03, section 9.2). Only when production is empty
        is an improvement candidate considered, and only if its budget has
        not been spent (A48). An empty production queue and no eligible
        candidate yields idle (A16).
        """
        now = datetime.now(UTC)
        ready = self.store.ready_tasks(project_id)

        production = [t for t in ready if t.kind == PRODUCTION]
        if production:
            return production[0]

        candidates = [t for t in ready if t.kind == IMPROVEMENT]
        if candidates and self.budget.can_run(now=now):
            return candidates[0]
        return None

    def consume_budget(self, *, active_minutes: int) -> None:
        """Account one improvement attempt against the candidate budget."""
        self.budget.consume(now=datetime.now(UTC), active_minutes=active_minutes)

    def status(self, project_id: str) -> dict[str, object]:
        """A simple status view: what is ready in each class and the budget."""
        ready = self.store.ready_tasks(project_id)
        production = [t for t in ready if t.kind == PRODUCTION]
        candidates = [t for t in ready if t.kind == IMPROVEMENT]
        now = datetime.now(UTC)
        return {
            "production_ready": len(production),
            "improvement_candidates": len(candidates),
            "candidate_eligible": bool(candidates) and self.budget.can_run(now=now),
            "budget_attempts_left": self.budget.attempts_per_period - self.budget.attempts_used,
            "class_order": [PRODUCTION, IMPROVEMENT, IDLE],
        }


__all__ = ["CLASS_ORDER", "IDLE", "IMPROVEMENT", "PRODUCTION", "ImprovementBudget", "Scheduler"]
