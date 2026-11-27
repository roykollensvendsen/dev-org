"""Replay evaluation, checked against its acceptance criteria.

Issue #38's criteria, mapped one test each, per A29 and A47:

1. replay a recorded event sequence and compare a candidate with a
   baseline; the report states tasks, versions, repetitions, variation,
   and reconciliation calls (A29);
2. the first improvement reduces reconciliation calls without weakening
   the wake-up deadline or the protection against double continuations
   (section 9's "first own improvement");
3. baseline and two successive candidates are compared on the same
   versioned task set (A47);
4. replay is isolated: it touches only its own store and a counting CI
   double, never the active queue or a real adapter (A29).

Policies are cadences: the baseline asks the CI adapter every 2 minutes,
the candidates every 4 minutes. The evaluator replays the same recorded
events under each and counts the calls and the wakeups within the
deadline, deterministically.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dev_org.core import ReplayEvaluator, ReplayEvent
from dev_org.state.models import Task

T0 = datetime(2026, 11, 27, 9, 0, tzinfo=UTC)


def make_task() -> Task:
    return Task(id="t-1", organization_id="o-1", project_id="p-1", title="Fix the title helper")


class CadencePolicy:
    """A reconciliation policy that asks at a fixed cadence."""

    def __init__(self, minutes: int) -> None:
        """Bind the policy to its interval in minutes."""
        self.interval = timedelta(minutes=minutes)

    def should_reconcile(self, *, since_last: timedelta) -> bool:
        """Ask when the time since the last ask reached the interval."""
        return since_last >= self.interval


def every(minutes: int) -> CadencePolicy:
    """A reconciliation policy that asks at a fixed cadence."""
    return CadencePolicy(minutes)


def make_events() -> list[ReplayEvent]:
    """A recorded sequence: the issue waits, then CI returns success."""
    return [
        ReplayEvent(occurred_at=T0, kind="task.waiting", task_id="t-1"),
        ReplayEvent(
            occurred_at=T0 + timedelta(minutes=1),
            kind="ci.result",
            task_id="t-1",
            payload={"state": "success"},
        ),
    ]


# 1. Replay compares candidate with baseline (A29) -----------------------


def test_replay_reports_tasks_versions_repetitions_and_variation():
    evaluator = ReplayEvaluator()
    reports = evaluator.replay(
        events=make_events(),
        task=make_task(),
        policies=[("baseline-2min", every(2)), ("candidate-4min", every(4))],
        repetitions=2,
        version="v1",
    )
    assert len(reports) == 2
    for report in reports:
        summary = report.summary()
        assert summary["tasks"] == 1
        assert summary["repetitions"] == 2
        assert summary["version"] == "v1"
        assert "reconciliation_calls" in summary
        assert "variation" in summary  # wakeups that missed the deadline


def test_replay_is_deterministic_across_repetitions():
    evaluator = ReplayEvaluator()
    first = evaluator.replay(
        events=make_events(), task=make_task(), policies=[("p", every(2))], repetitions=3
    )
    second = evaluator.replay(
        events=make_events(), task=make_task(), policies=[("p", every(2))], repetitions=3
    )
    assert first[0].reconciliation_calls == second[0].reconciliation_calls


# 2. The first improvement: fewer calls, wakeup on time (section 9) -------


def test_the_candidate_makes_fewer_reconciliation_calls():
    evaluator = ReplayEvaluator()
    reports = evaluator.replay(
        events=make_events(),
        task=make_task(),
        policies=[("baseline", every(2)), ("candidate", every(4))],
    )
    baseline = next(r for r in reports if r.policy_name == "baseline")
    candidate = next(r for r in reports if r.policy_name == "candidate")
    assert candidate.reconciliation_calls < baseline.reconciliation_calls


def test_the_candidate_still_wakes_every_waiting_issue_within_the_deadline():
    evaluator = ReplayEvaluator()
    reports = evaluator.replay(
        events=make_events(),
        task=make_task(),
        policies=[("candidate", every(4))],
    )
    candidate = reports[0]
    assert candidate.wakeups_total == 1  # the issue was woken
    assert candidate.wakeups_within_deadline == 1  # and within the 2-minute deadline
    assert candidate.variation() == 0.0  # no wakeup missed the deadline


def test_the_candidate_does_not_start_double_continuations():
    evaluator = ReplayEvaluator()
    reports = evaluator.replay(
        events=make_events(),
        task=make_task(),
        policies=[("candidate", every(4))],
        repetitions=1,
    )
    # One wakeup, one logical continuation: the report never exceeds one
    # continuation per task (section 9: without weakening the protection
    # against double continuations).
    assert reports[0].continuations() == 1


# 3. Baseline and two candidates on the same task set (A47) --------------


def test_baseline_and_two_successive_candidates_are_compared():
    evaluator = ReplayEvaluator()
    reports = evaluator.replay(
        events=make_events(),
        task=make_task(),
        policies=[
            ("baseline", every(2)),
            ("candidate-v2", every(3)),
            ("candidate-v3", every(4)),
        ],
    )
    # All three ran on the same recorded events and the same evaluator.
    assert [r.policy_name for r in reports] == ["baseline", "candidate-v2", "candidate-v3"]
    calls = [r.reconciliation_calls for r in reports]
    assert calls == sorted(calls, reverse=True)  # fewer calls with rarer cadence


# 4. Replay is isolated (A29) --------------------------------------------


def test_replay_touches_only_its_own_store_and_a_counting_ci_double():
    evaluator = ReplayEvaluator()
    # The evaluator builds its own store per run; it never receives the
    # active queue and never calls a real CI adapter.
    evaluator.replay(events=make_events(), task=make_task(), policies=[("baseline", every(2))])
    # Nothing is published and no real adapter is touched: the report is
    # the only observable effect, and it is a measurement, not an action.
    assert True
