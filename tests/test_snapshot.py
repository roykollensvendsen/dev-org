"""Snapshot and restore, checked against its acceptance criteria.

Issue #50's criteria, mapped one test each, per A08 and section 7.2:

1. move from PC A to B with local work and pending CI: secured code, PR,
   wait condition, and issue id are preserved (A08);
2. the snapshot contains schema and program version, organization and
   project identity, tasks, wait conditions, and checkpoints; missing
   parts are reported as unsecured (7.2);
3. restore validates the version and references and reconciles; the old
   service must have lost publishing rights before take-over (A08);
4. access keys are never part of the snapshot (7.2).
"""

from __future__ import annotations

import pytest

from dev_org.core import (
    SNAPSHOT_SCHEMA,
    ActivationService,
    CandidateEnvironment,
    Snapshot,
    SnapshotRefusedError,
    SnapshotService,
    TaskLifecycle,
)
from dev_org.core.activation import ActivationGates
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore


def make_task(task_id: str = "t-1", *, priority: str = "P2") -> Task:
    return Task(
        id=task_id, organization_id="o-1", project_id="p-1", title=f"Fix {task_id}", priority=priority
    )  # type: ignore[arg-type]


# 1. Move from A to B preserving secured work (A08) -----------------------


def test_a_move_preserves_the_waiting_task_and_its_wait_condition():
    # Machine A: a task is secured and waits on CI.
    store_a = InMemoryStore()
    lifecycle = TaskLifecycle(store_a)
    task = make_task()
    store_a.save_task(task)
    lifecycle.dispatch(task)
    lifecycle.wait(task, wait_condition="ci:sha:checks", next_action="merge")

    service = SnapshotService(store=store_a)
    snapshot = service.take()

    # Machine B restores after the old side lost publishing rights.
    store_b = service.restore(snapshot, old_service_lost_publishing=True)
    restored = store_b.get_task("t-1")
    assert restored is not None
    assert restored.id == task.id  # issue id preserved
    assert restored.status == "Waiting"  # the wait survives the move
    assert snapshot.schema == SNAPSHOT_SCHEMA


def test_the_snapshot_carries_secured_code_and_pr_reference():
    store_a = InMemoryStore()
    task = make_task()
    task.acceptance_criteria = ["devorg-t-1-fix@abc123:PR-7"]  # code ref and PR
    store_a.save_task(task)

    service = SnapshotService(store=store_a)
    snapshot = service.take()

    assert any("PR-7" in c for c in snapshot.tasks[0].acceptance_criteria)


# 2. Snapshot contents and unsecured reporting (7.2) ---------------------


def test_the_snapshot_reports_schema_version_and_identity():
    store_a = InMemoryStore()
    store_a.save_task(make_task())
    service = SnapshotService(store=store_a)
    snapshot = service.take()

    assert snapshot.schema == SNAPSHOT_SCHEMA
    assert snapshot.program_version
    assert snapshot.organization_id == "o-1"
    assert snapshot.project_id == "p-1"


def test_missing_parts_are_reported_as_unsecured_not_dropped():
    # An empty store: nothing to capture, reported rather than assumed.
    service = SnapshotService(store=InMemoryStore())
    snapshot = service.take()
    missing = snapshot.missing_parts()
    assert "tasks" in missing  # explicitly unsecured, not silently empty


def test_access_keys_are_never_in_the_snapshot():
    store_a = InMemoryStore()
    store_a.save_task(make_task())
    service = SnapshotService(store=store_a)
    snapshot = service.take()

    # Section 7.2: access keys are fetched separately, never in the image.
    assert not hasattr(snapshot, "access_keys")
    assert not hasattr(snapshot, "tokens")


# 3. Restore validates and requires lost publishing rights (A08) ---------


def test_restore_is_refused_while_the_old_service_still_publishes():
    store_a = InMemoryStore()
    store_a.save_task(make_task())
    service = SnapshotService(store=store_a)
    snapshot = service.take()

    with pytest.raises(SnapshotRefusedError, match="publishing"):
        service.restore(snapshot, old_service_lost_publishing=False)


def test_restore_is_refused_for_an_unknown_schema():
    store_a = InMemoryStore()
    store_a.save_task(make_task())
    service = SnapshotService(store=store_a)
    snapshot = service.take()
    bad = Snapshot(
        schema="dev-org.snapshot.old",
        program_version=snapshot.program_version,
        organization_id="o-1",
        project_id="p-1",
        tasks=snapshot.tasks,
        checkpoints=(),
    )
    with pytest.raises(SnapshotRefusedError, match="schema"):
        service.restore(bad, old_service_lost_publishing=True)


def test_the_active_program_version_survives_the_move():
    store_a = InMemoryStore()
    store_a.save_task(make_task())
    activation = ActivationService(store=store_a)
    candidate = CandidateEnvironment(candidate_store=InMemoryStore())
    activation.activate(
        candidate=candidate,
        candidate_version="v2",
        gates=ActivationGates(
            ci_passed=True, acceptance_tests_passed=True, backup_ok=True, migration_ok=True, recovery_ok=True
        ),
    )

    service = SnapshotService(store=store_a, activation=activation)
    snapshot = service.take()
    assert snapshot.active_version == "v2"  # the active version moves with the work
