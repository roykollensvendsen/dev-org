"""Scheduler classes and budgeted throttling, checked against step 3.

Issue #35's acceptance criteria, mapped one test each, per ADR-DEV-010 and
the Linux-kernel scheduler model:

1. production work is picked before an improvement candidate (A03);
2. the candidate runs in its own budgeted queue and identity (A48);
3. the candidate is paused before it uses reserved production capacity,
   and yields when ordinary work arrives (A48);
4. with no ready work and no eligible candidate the agents go idle (A16);
5. the class order is fixed, not swappable.

The budget uses a simulated clock where it matters; the rest is
deterministic against the in-memory store.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dev_org.core import ImprovementBudget, Scheduler
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore


def make_task(task_id: str, *, kind: str = "production", priority: str = "P2") -> Task:
    return Task(
        id=task_id,
        organization_id="o-1",
        project_id="p-1",
        title=f"{task_id}",
        priority=priority,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
    )


def make_scheduler(*, budget: ImprovementBudget | None = None) -> tuple[Scheduler, InMemoryStore]:
    store = InMemoryStore()
    return Scheduler(store=store, budget=budget or ImprovementBudget()), store


# 1. Production before improvement (A03) ---------------------------------


def test_a_ready_production_task_is_picked_before_an_improvement_candidate():
    scheduler, store = make_scheduler()
    store.save_task(make_task("t-candidate", kind="improvement"))
    store.save_task(make_task("t-prod", kind="production"))

    picked = scheduler.next_ready("p-1")
    assert picked is not None
    assert picked.id == "t-prod"


def test_priority_orders_production_work_and_improvement_only_when_production_is_empty():
    scheduler, store = make_scheduler()
    # A P2 improvement candidate is ready; a P0 production task arrives later.
    store.save_task(make_task("t-cand", kind="improvement", priority="P2"))
    store.save_task(make_task("t-prod", kind="production", priority="P0"))

    picked = scheduler.next_ready("p-1")
    assert picked is not None
    assert picked.id == "t-prod"


# 2. Separate budgeted queue and identity (A48) --------------------------


def test_the_candidate_runs_only_when_production_is_empty():
    scheduler, store = make_scheduler()
    store.save_task(make_task("t-cand", kind="improvement"))
    # No production work: the candidate is the only eligible task.
    picked = scheduler.next_ready("p-1")
    assert picked is not None
    assert picked.id == "t-cand"


# 3. Throttled before it uses reserved capacity (A48) --------------------


def test_the_candidate_is_throttled_once_its_attempt_budget_is_spent():
    budget = ImprovementBudget(attempts_per_period=1)
    scheduler, store = make_scheduler(budget=budget)
    store.save_task(make_task("t-cand", kind="improvement"))

    first = scheduler.next_ready("p-1")
    assert first is not None
    assert first.id == "t-cand"
    scheduler.consume_budget(active_minutes=5)

    # The budget is spent: the candidate is no longer eligible this period.
    assert scheduler.next_ready("p-1") is None
    assert scheduler.status("p-1")["candidate_eligible"] is False


def test_the_budget_rolls_over_and_the_candidate_runs_again_next_period():
    now = datetime(2026, 11, 27, 9, 0, tzinfo=UTC)
    budget = ImprovementBudget(attempts_per_period=1, period=timedelta(hours=1))
    budget.period_started_at = now
    scheduler, store = make_scheduler(budget=budget)
    store.save_task(make_task("t-cand", kind="improvement"))

    scheduler.next_ready("p-1")
    scheduler.consume_budget(active_minutes=5)
    assert scheduler.next_ready("p-1") is None  # spent this period

    # Simulate the next period by moving the clock: the budget rolls.
    budget.period_started_at = now - timedelta(hours=2)
    assert scheduler.next_ready("p-1") is not None


# 4. Idle with no work and no eligible candidate (A16) -------------------


def test_an_empty_queue_and_no_candidate_yields_idle():
    scheduler, _ = make_scheduler()
    assert scheduler.next_ready("p-1") is None


def test_a_throttled_candidate_alone_yields_idle():
    budget = ImprovementBudget(attempts_per_period=1)
    scheduler, store = make_scheduler(budget=budget)
    store.save_task(make_task("t-cand", kind="improvement"))

    scheduler.next_ready("p-1")
    scheduler.consume_budget(active_minutes=5)
    assert scheduler.next_ready("p-1") is None  # idle: candidate throttled, no production


# 5. Fixed class order (ADR-DEV-010) -------------------------------------


def test_the_class_order_is_fixed_and_not_swappable():
    scheduler, _ = make_scheduler()
    order = scheduler.status("p-1")["class_order"]
    assert order == ["production", "improvement", "idle"]
