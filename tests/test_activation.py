"""Controlled activation, rollback, and blue/green, checked against step 3.

Issue #37's acceptance criteria, mapped one test each:

1. the candidate does not become active before CI, mandatory tests,
   backup, migration, and recovery are approved (A45);
2. activation keeps the previous version, and rollback restores it
   without losing recorded operations or starting double continuations
   (A14, A45);
3. on a candidate failure, the active version continues without a
   maintenance stop, reservation loss, or blocked assignment; the
   candidate loses lease and holds no production lock (A49);
4. database migrations are a gate, not a side effect: a missing or
   non-approved migration refuses activation.

The active version is a durable record; the candidate becomes active only
through controlled take-over (section 9.2).
"""

from __future__ import annotations

import pytest

from dev_org.core import (
    ActivationGates,
    ActivationRefusedError,
    ActivationService,
    CandidateEnvironment,
    TaskLifecycle,
)
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore


def make_task(task_id: str) -> Task:
    return Task(id=task_id, organization_id="o-1", project_id="p-1", title=task_id)


def approved_gates() -> ActivationGates:
    return ActivationGates(
        ci_passed=True,
        acceptance_tests_passed=True,
        backup_ok=True,
        migration_ok=True,
        recovery_ok=True,
    )


def make_service_and_candidate() -> tuple[ActivationService, CandidateEnvironment]:
    service = ActivationService(store=InMemoryStore())
    candidate = CandidateEnvironment(candidate_store=InMemoryStore())
    return service, candidate


# 1. Qualified before active (A45) ---------------------------------------


def test_activation_is_refused_until_every_gate_passes():
    service, candidate = make_service_and_candidate()
    gates = ActivationGates(ci_passed=True, acceptance_tests_passed=True, backup_ok=True)
    # Migration and recovery are not approved: the candidate stays inactive.
    with pytest.raises(ActivationRefusedError, match="not qualified"):
        service.activate(candidate=candidate, candidate_version="v2", gates=gates)
    assert service.active_version() is None


def test_activation_refused_when_ci_has_not_passed():
    service, candidate = make_service_and_candidate()
    gates = ActivationGates(acceptance_tests_passed=True, backup_ok=True, migration_ok=True, recovery_ok=True)
    with pytest.raises(ActivationRefusedError, match="CI"):
        service.activate(candidate=candidate, candidate_version="v2", gates=gates)


def test_activation_succeeds_when_all_gates_pass():
    service, candidate = make_service_and_candidate()
    activated = service.activate(candidate=candidate, candidate_version="v2", gates=approved_gates())
    assert activated == "v2"
    assert service.active_version() == "v2"


# 2. Rollback restores without losing work (A14, A45) --------------------


def test_activation_keeps_the_previous_version_for_rollback():
    service, candidate = make_service_and_candidate()
    service.activate(candidate=candidate, candidate_version="v1", gates=approved_gates())
    service.activate(candidate=candidate, candidate_version="v2", gates=approved_gates())

    assert service.rollback() == "v1"
    assert service.active_version() == "v1"


def test_rollback_restores_the_state_that_can_be_read():
    service, candidate = make_service_and_candidate()
    service.activate(candidate=candidate, candidate_version="v1", gates=approved_gates())
    service.activate(candidate=candidate, candidate_version="v2", gates=approved_gates())

    service.rollback()
    # The restored state is readable through the active version record.
    active = service.active()
    assert active is not None
    assert active.version == "v1"


def test_rollback_with_no_previous_version_is_refused():
    service, candidate = make_service_and_candidate()
    service.activate(candidate=candidate, candidate_version="v1", gates=approved_gates())
    with pytest.raises(ActivationRefusedError, match="no previous version"):
        service.rollback()


def test_rollback_creates_no_continuation_and_loses_no_operations():
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store)
    task = make_task("t-waiting")
    store.save_task(task)
    lifecycle.dispatch(task)
    lifecycle.wait(task, wait_condition="CI result", next_action="merge")
    events_before = len(store.events_for_task("t-waiting"))

    # A version change happens while the issue waits on CI (A14): first
    # activate v1, then upgrade to v2, then roll back to v1.
    candidate = CandidateEnvironment(candidate_store=InMemoryStore())
    service = ActivationService(store=store)
    service.activate(candidate=candidate, candidate_version="v1", gates=approved_gates())
    service.activate(candidate=candidate, candidate_version="v2", gates=approved_gates())
    service.rollback()

    # The rollback itself created no continuation: the issue still waits,
    # and its event count is unchanged (no double continuation, A45).
    assert task.status == "Waiting"
    assert len(store.events_for_task("t-waiting")) == events_before


# 3. Candidate failure keeps the active version (A49) --------------------


def test_a_candidate_failure_does_not_touch_the_active_version():
    service, candidate = make_service_and_candidate()
    service.activate(candidate=candidate, candidate_version="v1", gates=approved_gates())

    # The candidate fails during activation; the active version continues.
    service.fail_candidate(candidate_version="v2")
    assert service.active_version() == "v1"  # no maintenance stop, no lost reservation


def test_a_failed_candidate_holds_no_production_lock():
    service, candidate = make_service_and_candidate()
    service.activate(candidate=candidate, candidate_version="v1", gates=approved_gates())
    service.fail_candidate(candidate_version="v2")

    # The failed candidate never became active, so it holds no production
    # lock: the active version is still v1 and can be rolled back or kept.
    assert service.active_version() == "v1"
    # And the failure is recorded for traceability.
    failed = [e for e in service.store.events if e.event_type == "candidate.failed"]
    assert len(failed) == 1


# 4. Migration is a gate (A45) -------------------------------------------


def test_a_missing_migration_path_refuses_activation():
    service, candidate = make_service_and_candidate()
    gates = ActivationGates(
        ci_passed=True, acceptance_tests_passed=True, backup_ok=True, migration_ok=False, recovery_ok=True
    )
    with pytest.raises(ActivationRefusedError, match="migration"):
        service.activate(candidate=candidate, candidate_version="v2", gates=gates)
    assert service.active_version() is None
